package main

import (
	"bytes"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"unsafe"
)

const (
	ioctlTIOCGPTN   = 0x80045430
	ioctlTIOCSPTLCK = 0x40045431
	ioctlTIOCSWINSZ = 0x5414
)

func handleShell(w http.ResponseWriter, r *http.Request) {
	hijacker, ok := w.(http.Hijacker)
	if !ok {
		http.Error(w, "hijack unsupported", http.StatusInternalServerError)
		return
	}
	key := r.Header.Get("Sec-WebSocket-Key")
	if key == "" {
		http.Error(w, "websocket key required", http.StatusBadRequest)
		return
	}
	conn, rw, err := hijacker.Hijack()
	if err != nil {
		return
	}
	defer conn.Close()

	_, _ = rw.WriteString("HTTP/1.1 101 Switching Protocols\r\n")
	_, _ = rw.WriteString("Upgrade: websocket\r\n")
	_, _ = rw.WriteString("Connection: Upgrade\r\n")
	_, _ = rw.WriteString("Sec-WebSocket-Accept: " + websocketAccept(key) + "\r\n\r\n")
	_ = rw.Flush()

	ptmx, pts, err := openPTY()
	if err != nil {
		_ = writeWebSocketFrame(conn, websocketOpcodeClose, nil)
		return
	}
	defer ptmx.Close()

	cmd := shellCommand()
	cmd.Env = append(os.Environ(), egressState.RuntimeEnvironmentOverlay()...)
	cmd.Env = append(cmd.Env, "TERM=xterm-256color")
	cmd.Stdin = pts
	cmd.Stdout = pts
	cmd.Stderr = pts
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true, Setctty: true}
	if err := cmd.Start(); err != nil {
		pts.Close()
		_ = writeWebSocketFrame(conn, websocketOpcodeClose, nil)
		return
	}
	pts.Close()
	defer func() {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
	}()

	done := make(chan struct{})
	var writeMu sync.Mutex
	writeFrame := func(opcode byte, payload []byte) error {
		writeMu.Lock()
		defer writeMu.Unlock()
		return writeWebSocketFrame(conn, opcode, payload)
	}

	// PTY reader: forwards shell output to WebSocket client.
	go func() {
		defer close(done)
		buf := make([]byte, 4096)
		for {
			n, err := ptmx.Read(buf)
			if n > 0 {
				if writeFrame(2, buf[:n]) != nil {
					return
				}
			}
			if err != nil {
				return
			}
		}
	}()

	// WebSocket reader: forwards client input to PTY, handles resize.
	go func() {
		for {
			data, opcode, err := readWebSocketFrame(conn)
			if err != nil {
				_ = cmd.Process.Kill()
				return
			}
			if opcode == websocketOpcodeClose {
				_ = cmd.Process.Kill()
				return
			}
			if opcode == websocketOpcodePing {
				_ = writeFrame(websocketOpcodePong, data)
				continue
			}
			if opcode == websocketOpcodePong {
				continue
			}
			if isResizeMessage(data) {
				applyResize(ptmx, data)
				continue
			}
			_, _ = ptmx.Write(data)
		}
	}()

	<-done
}

func shellCommand() *exec.Cmd {
	shell := "/bin/sh"
	if _, err := exec.LookPath("bash"); err == nil {
		shell = "bash"
	}
	return exec.Command(shell, "-l")
}

func openPTY() (master *os.File, slave *os.File, err error) {
	ptmx, err := os.OpenFile("/dev/ptmx", os.O_RDWR, 0)
	if err != nil {
		return nil, nil, err
	}

	var ptsNum uint32
	if _, _, errno := syscall.Syscall(syscall.SYS_IOCTL, ptmx.Fd(), ioctlTIOCGPTN, uintptr(unsafe.Pointer(&ptsNum))); errno != 0 {
		ptmx.Close()
		return nil, nil, fmt.Errorf("TIOCGPTN: %v", errno)
	}

	var unlock int
	if _, _, errno := syscall.Syscall(syscall.SYS_IOCTL, ptmx.Fd(), ioctlTIOCSPTLCK, uintptr(unsafe.Pointer(&unlock))); errno != 0 {
		ptmx.Close()
		return nil, nil, fmt.Errorf("TIOCSPTLCK: %v", errno)
	}

	pts, err := os.OpenFile(fmt.Sprintf("/dev/pts/%d", ptsNum), os.O_RDWR|syscall.O_NOCTTY, 0)
	if err != nil {
		ptmx.Close()
		return nil, nil, err
	}
	return ptmx, pts, nil
}

func isResizeMessage(data []byte) bool {
	return bytes.HasPrefix(data, []byte("\x00resize:"))
}

func applyResize(ptmx *os.File, data []byte) {
	msg := string(data[len("\x00resize:"):])
	parts := strings.SplitN(msg, ":", 2)
	if len(parts) != 2 {
		return
	}
	rows, err1 := strconv.Atoi(parts[0])
	cols, err2 := strconv.Atoi(parts[1])
	if err1 != nil || err2 != nil || rows < 1 || cols < 1 {
		return
	}
	setTerminalSize(ptmx, rows, cols)
}

func setTerminalSize(f *os.File, rows, cols int) {
	ws := struct {
		Row    uint16
		Col    uint16
		Xpixel uint16
		Ypixel uint16
	}{Row: uint16(rows), Col: uint16(cols)}
	_, _, _ = syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), ioctlTIOCSWINSZ, uintptr(unsafe.Pointer(&ws)))
}
