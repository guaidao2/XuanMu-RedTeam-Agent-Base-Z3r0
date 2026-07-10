package main

import (
	"crypto/sha1"
	"encoding/base64"
	"encoding/binary"
	"fmt"
	"io"
)

func websocketAccept(key string) string {
	sum := sha1.Sum([]byte(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"))
	return base64.StdEncoding.EncodeToString(sum[:])
}

const maxWebSocketFrameSize = 1 << 20 // 1 MiB

const (
	websocketOpcodeClose = 8
	websocketOpcodePing  = 9
	websocketOpcodePong  = 10
)

func readWebSocketFrame(reader io.Reader) ([]byte, byte, error) {
	header := make([]byte, 2)
	if _, err := io.ReadFull(reader, header); err != nil {
		return nil, 0, err
	}
	opcode := header[0] & 0x0f
	masked := header[1]&0x80 != 0
	length := uint64(header[1] & 0x7f)

	if length == 126 {
		ext := make([]byte, 2)
		if _, err := io.ReadFull(reader, ext); err != nil {
			return nil, 0, err
		}
		length = uint64(binary.BigEndian.Uint16(ext))
	} else if length == 127 {
		ext := make([]byte, 8)
		if _, err := io.ReadFull(reader, ext); err != nil {
			return nil, 0, err
		}
		length = binary.BigEndian.Uint64(ext)
	}

	if length > maxWebSocketFrameSize {
		return nil, 0, fmt.Errorf("frame too large: %d bytes", length)
	}

	var mask [4]byte
	if masked {
		if _, err := io.ReadFull(reader, mask[:]); err != nil {
			return nil, 0, err
		}
	}

	payload := make([]byte, length)
	if _, err := io.ReadFull(reader, payload); err != nil {
		return nil, 0, err
	}
	if masked {
		for i := range payload {
			payload[i] ^= mask[i%4]
		}
	}
	return payload, opcode, nil
}

func writeWebSocketFrame(writer io.Writer, opcode byte, payload []byte) error {
	header := []byte{0x80 | opcode}
	length := len(payload)
	switch {
	case length < 126:
		header = append(header, byte(length))
	case length <= 65535:
		header = append(header, 126, byte(length>>8), byte(length))
	default:
		header = append(header, 127)
		ext := make([]byte, 8)
		binary.BigEndian.PutUint64(ext, uint64(length))
		header = append(header, ext...)
	}
	if _, err := writer.Write(header); err != nil {
		return err
	}
	_, err := writer.Write(payload)
	return err
}
