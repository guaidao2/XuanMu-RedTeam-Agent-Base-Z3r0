package main

import (
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

const (
	defaultControlProxyAddr = ":8000"
	defaultNoVNCTarget      = "http://127.0.0.1:8080"
	noVNCPathPrefix         = "/novnc"
	websockifyPath          = "/websockify"
	tokenEnvName            = "SANDBOX_CONTROL_PROXY_TOKEN"
)

func main() {
	token := os.Getenv(tokenEnvName)
	if token == "" {
		log.Fatalf("%s is required", tokenEnvName)
	}

	noVNCTarget := mustParseURL(defaultNoVNCTarget)
	passthroughProxy := withAuth(token, newEntryProxy(noVNCTarget))
	noVNCProxy := withAuth(token, newEntryPrefixProxy(noVNCPathPrefix, noVNCTarget))
	mux := newServerMux(token, passthroughProxy, noVNCProxy)
	egressServer := newEgressProxyServer()

	server := &http.Server{
		Addr:              defaultControlProxyAddr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Printf("sandbox egress listening on %s", defaultEgressProxyAddr)
		if err := egressServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("sandbox egress failed: %v", err)
		}
	}()

	log.Printf("sandbox control proxy listening on %s", defaultControlProxyAddr)
	log.Printf("sandbox control proxy novnc target=%s", noVNCTarget)
	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("sandbox control proxy failed: %v", err)
	}
}

func newServerMux(token string, passthroughProxy http.Handler, noVNCProxy http.Handler) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/", withAuthFunc(token, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		http.Redirect(w, r, noVNCPathPrefix+"/vnc.html?autoconnect=true&resize=remote&path=websockify", http.StatusFound)
	}))
	mux.HandleFunc("/healthz", withAuthFunc(token, func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok"))
	}))
	mux.HandleFunc("/shell", withAuthFunc(token, handleShell))
	mux.HandleFunc("/files", withAuthFunc(token, handleListFiles))
	mux.HandleFunc("/files/info", withAuthFunc(token, handleFileInfo))
	mux.HandleFunc("/files/read", withAuthFunc(token, handleReadFile))
	mux.HandleFunc("/files/write", withAuthFunc(token, handleWriteFile))
	mux.HandleFunc("/files/upload", withAuthFunc(token, handleUploadFiles))
	mux.HandleFunc("/files/download", withAuthFunc(token, handleDownloadFiles))
	mux.HandleFunc("/files/copy", withAuthFunc(token, handleCopyFiles))
	mux.HandleFunc("/files/move", withAuthFunc(token, handleMoveFiles))
	mux.HandleFunc("/files/delete", withAuthFunc(token, handleDeleteFiles))
	mux.HandleFunc("/files/mkdir", withAuthFunc(token, handleMkdir))
	mux.HandleFunc("/egress", withAuthFunc(token, handleEgress))
	mux.Handle(noVNCPathPrefix+"/", noVNCProxy)
	mux.HandleFunc(noVNCPathPrefix, withAuthFunc(token, func(w http.ResponseWriter, r *http.Request) {
		target := noVNCPathPrefix + "/"
		if r.URL.RawQuery != "" {
			target += "?" + r.URL.RawQuery
		}
		http.Redirect(w, r, target, http.StatusPermanentRedirect)
	}))
	mux.Handle(websockifyPath, passthroughProxy)
	return mux
}

func withAuth(token string, next http.Handler) http.Handler {
	return withAuthFunc(token, next.ServeHTTP)
}

func withAuthFunc(token string, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !authorized(r, token) {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		next(w, r)
	}
}

func authorized(r *http.Request, token string) bool {
	if r.URL.Query().Get("token") == token {
		return true
	}
	if r.Header.Get("X-Sandbox-Token") == token {
		return true
	}
	auth := r.Header.Get("Authorization")
	return strings.TrimSpace(strings.TrimPrefix(auth, "Bearer ")) == token
}
