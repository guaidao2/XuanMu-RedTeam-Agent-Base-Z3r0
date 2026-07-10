package main

import (
	"archive/tar"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type fileInfo struct {
	Name        string `json:"name"`
	Type        string `json:"type"`
	Size        int64  `json:"size"`
	ModifiedAt  int64  `json:"modified_at"`
	Owner       string `json:"owner"`
	Group       string `json:"group"`
	Permissions string `json:"permissions"`
	Path        string `json:"path"`
}

type uploadItem struct {
	Name string `json:"name"`
	Path string `json:"path"`
	Size int64  `json:"size"`
}

func handleListFiles(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodGet) {
		return
	}
	path := normalizePath(r.URL.Query().Get("path"))
	entries, err := os.ReadDir(path)
	if err != nil {
		writeFileError(w, err)
		return
	}
	files := make([]fileInfo, 0, len(entries))
	for _, entry := range entries {
		info, err := entry.Info()
		if err != nil {
			continue
		}
		files = append(files, toFileInfo(filepath.Join(path, entry.Name()), info))
	}
	writeJSON(w, map[string]any{"path": path, "files": files})
}

func handleFileInfo(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodGet) {
		return
	}
	path := normalizePath(r.URL.Query().Get("path"))
	info, err := os.Lstat(path)
	if err != nil {
		writeFileError(w, err)
		return
	}
	writeJSON(w, map[string]any{"file": toFileInfo(path, info)})
}

func handleReadFile(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodGet) {
		return
	}
	path := normalizePath(r.URL.Query().Get("path"))
	maxBytes := parseInt(r.URL.Query().Get("max_bytes"), 1048576)
	base64Mode := r.URL.Query().Get("base64") == "true"

	file, err := os.Open(path)
	if err != nil {
		writeFileError(w, err)
		return
	}
	defer file.Close()

	payload, err := io.ReadAll(io.LimitReader(file, int64(maxBytes)))
	if err != nil {
		writeFileError(w, err)
		return
	}
	content := string(payload)
	if base64Mode {
		content = base64.StdEncoding.EncodeToString(payload)
	}
	writeJSON(w, map[string]any{"path": path, "content": content, "size": len(payload)})
}

func handleWriteFile(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost) {
		return
	}
	var body struct {
		Path    string `json:"path"`
		Content string `json:"content"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	path := normalizePath(body.Path)
	if err := os.WriteFile(path, []byte(body.Content), 0o644); err != nil {
		writeFileError(w, err)
		return
	}
	writeJSON(w, map[string]any{"ok": true})
}

func handleUploadFiles(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost) {
		return
	}
	if err := r.ParseMultipartForm(64 << 20); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	path := normalizePath(r.FormValue("path"))
	overwrite := r.FormValue("overwrite") != "false"
	uploaded := []uploadItem{}
	for _, headers := range r.MultipartForm.File {
		for _, header := range headers {
			item, err := saveUploadedFile(header, path, overwrite)
			if err != nil {
				writeFileError(w, err)
				return
			}
			uploaded = append(uploaded, item)
		}
	}
	writeJSON(w, map[string]any{"path": path, "files": uploaded})
}

func handleDownloadFiles(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodGet) {
		return
	}
	paths := r.URL.Query()["path"]
	if len(paths) == 0 {
		http.Error(w, "download path is required", http.StatusBadRequest)
		return
	}
	if len(paths) == 1 {
		path := normalizePath(paths[0])
		info, err := os.Lstat(path)
		if err != nil {
			writeFileError(w, err)
			return
		}
		if !info.IsDir() {
			w.Header().Set("Content-Type", "application/octet-stream")
			w.Header().Set("Content-Disposition", fmt.Sprintf("attachment; filename=%q", filepath.Base(path)))
			http.ServeFile(w, r, path)
			return
		}
	}
	w.Header().Set("Content-Type", "application/x-tar")
	w.Header().Set("Content-Disposition", `attachment; filename="container-files.tar"`)
	tw := tar.NewWriter(w)
	defer tw.Close()
	for _, raw := range paths {
		path := normalizePath(raw)
		rootName := filepath.Base(path)
		_ = filepath.Walk(path, func(current string, info os.FileInfo, err error) error {
			if err != nil {
				return nil
			}
			rel, _ := filepath.Rel(path, current)
			name := rootName
			if rel != "." {
				name = filepath.Join(rootName, rel)
			}
			hdr, err := tar.FileInfoHeader(info, "")
			if err != nil {
				return nil
			}
			hdr.Name = filepath.ToSlash(name)
			if err := tw.WriteHeader(hdr); err != nil {
				return nil
			}
			if info.IsDir() {
				return nil
			}
			f, err := os.Open(current)
			if err != nil {
				return nil
			}
			defer f.Close()
			_, _ = io.Copy(tw, f)
			return nil
		})
	}
}

func handleCopyFiles(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost) {
		return
	}
	var body struct {
		Sources     []string `json:"sources"`
		Destination string   `json:"destination"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	for _, src := range body.Sources {
		if err := copyPath(normalizePath(src), normalizePath(body.Destination)); err != nil {
			writeFileError(w, err)
			return
		}
	}
	writeJSON(w, map[string]any{"ok": true})
}

func handleMoveFiles(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost) {
		return
	}
	var body struct {
		Sources     []string `json:"sources"`
		Destination string   `json:"destination"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	dest := normalizePath(body.Destination)
	for _, src := range body.Sources {
		target := filepath.Join(dest, filepath.Base(src))
		if err := os.Rename(normalizePath(src), target); err != nil {
			writeFileError(w, err)
			return
		}
	}
	writeJSON(w, map[string]any{"ok": true})
}

func handleDeleteFiles(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost) {
		return
	}
	var body struct {
		Paths []string `json:"paths"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	for _, p := range body.Paths {
		if err := os.RemoveAll(normalizePath(p)); err != nil {
			writeFileError(w, err)
			return
		}
	}
	writeJSON(w, map[string]any{"ok": true})
}

func handleMkdir(w http.ResponseWriter, r *http.Request) {
	if !requireMethod(w, r, http.MethodPost) {
		return
	}
	var body struct {
		Path string `json:"path"`
	}
	if !decodeJSON(w, r, &body) {
		return
	}
	if err := os.MkdirAll(normalizePath(body.Path), 0o755); err != nil {
		writeFileError(w, err)
		return
	}
	writeJSON(w, map[string]any{"ok": true})
}

// --- File operation helpers ---

func toFileInfo(path string, info os.FileInfo) fileInfo {
	ft := "file"
	if info.IsDir() {
		ft = "directory"
	} else if info.Mode()&os.ModeSymlink != 0 {
		ft = "symlink"
	}
	return fileInfo{
		Name:        filepath.Base(path),
		Type:        ft,
		Size:        info.Size(),
		ModifiedAt:  info.ModTime().Unix(),
		Owner:       "",
		Group:       "",
		Permissions: fmt.Sprintf("%#o", info.Mode().Perm()),
		Path:        path,
	}
}

func saveUploadedFile(header *multipart.FileHeader, dest string, overwrite bool) (uploadItem, error) {
	name := filepath.Base(header.Filename)
	target := filepath.Join(dest, name)
	if !overwrite {
		if _, err := os.Stat(target); err == nil {
			return uploadItem{}, errors.New("file already exists")
		}
	}
	src, err := header.Open()
	if err != nil {
		return uploadItem{}, err
	}
	defer src.Close()
	f, err := os.Create(target)
	if err != nil {
		return uploadItem{}, err
	}
	defer f.Close()
	size, err := io.Copy(f, src)
	if err != nil {
		return uploadItem{}, err
	}
	return uploadItem{Name: name, Path: target, Size: size}, nil
}

func copyPath(src string, dest string) error {
	info, err := os.Lstat(src)
	if err != nil {
		return err
	}
	target := filepath.Join(dest, filepath.Base(src))
	if info.IsDir() {
		return copyDir(src, target)
	}
	return copyFile(src, target, info.Mode())
}

func copyDir(src string, dest string) error {
	return filepath.Walk(src, func(current string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(src, current)
		target := filepath.Join(dest, rel)
		if info.IsDir() {
			return os.MkdirAll(target, info.Mode())
		}
		return copyFile(current, target, info.Mode())
	})
}

func copyFile(src string, dest string, mode os.FileMode) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(dest), 0o755); err != nil {
		return err
	}
	out, err := os.OpenFile(dest, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, mode)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, in)
	return err
}

// --- HTTP helpers ---

func normalizePath(path string) string {
	if strings.TrimSpace(path) == "" {
		return "/"
	}
	cleaned := filepath.Clean("/" + strings.TrimPrefix(path, "/"))
	if cleaned == "." {
		return "/"
	}
	return cleaned
}

func decodeJSON(w http.ResponseWriter, r *http.Request, target any) bool {
	if err := json.NewDecoder(r.Body).Decode(target); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, payload any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(payload)
}

func writeFileError(w http.ResponseWriter, err error) {
	if os.IsNotExist(err) {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}
	if strings.Contains(err.Error(), "already exists") {
		http.Error(w, err.Error(), http.StatusConflict)
		return
	}
	http.Error(w, err.Error(), http.StatusBadRequest)
}

func parseInt(value string, fallback int) int {
	n, err := strconv.Atoi(value)
	if err != nil || n <= 0 {
		return fallback
	}
	return n
}

func requireMethod(w http.ResponseWriter, r *http.Request, method string) bool {
	if r.Method == method {
		return true
	}
	http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	return false
}
