package main

import (
	"log"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
)

func newEntryProxy(target *url.URL) http.Handler {
	proxy := httputil.NewSingleHostReverseProxy(target)
	proxy.Transport = directHTTPTransport()
	orig := proxy.Director
	proxy.Director = func(r *http.Request) {
		orig(r)
		r.Host = target.Host
	}
	return proxy
}

func newEntryPrefixProxy(prefix string, target *url.URL) http.Handler {
	proxy := httputil.NewSingleHostReverseProxy(target)
	proxy.Transport = directHTTPTransport()
	orig := proxy.Director
	proxy.Director = func(r *http.Request) {
		orig(r)
		r.URL.Path = trimEntryPrefix(r.URL.Path, prefix)
		r.URL.RawPath = ""
		r.Host = target.Host
	}
	return proxy
}

func directHTTPTransport() *http.Transport {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	return transport
}

func trimEntryPrefix(path string, prefix string) string {
	if path == prefix {
		return "/"
	}
	if strings.HasPrefix(path, prefix+"/") {
		trimmed := strings.TrimPrefix(path, prefix)
		if trimmed == "" {
			return "/"
		}
		return trimmed
	}
	return path
}

func mustParseURL(rawURL string) *url.URL {
	u, err := url.Parse(rawURL)
	if err != nil {
		log.Fatalf("invalid target url %q: %v", rawURL, err)
	}
	return u
}
