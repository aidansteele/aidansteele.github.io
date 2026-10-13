---
layout: post
title: Go on Lambda Web Functions via execve()
date:
  created: 2026-10-12T23:50:00
categories:
  - AWS
---

In [my notes on Lambda Web Functions][main-post-ric] I mentioned that the
runtime contract is: Lambda `import()`s `/var/task/index.js`, then waits for
something to accept a TCP connection on `AWS_LAMBDA_HTTP_ENDPOINT`. The
[launch][launch] says Web Functions are Node.js only, which I took as a personal
challenge.

<!-- more -->

## "Node.js only" is a soft limit

I wrote a hello-world HTTP server in Go, cross-compiled it, and put it in the
zip next to this one-line `index.js`:

```javascript
process.execve("/var/task/server", ["/var/task/server"], process.env);
```

Node 24 has [`process.execve()`](https://nodejs.org/docs/latest-v24.x/api/process.html#processexecvefile-args-env),
which replaces the process image the way the libc call does, so after that
line there is no Node left to pay for. On its own this gets you a
`Runtime.InitTimeout`, because the runtime interface client's last
job - the `POST /2025-09-01/ready` after the port probe passes - never happens;
the RIC was in the process that just got replaced. The `/load` step *has* happened,
so your environment variables are already in `process.env` and come along for
the ride, but the Go server has to announce itself once it's listening. Here's
the whole thing:

```go
package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		log.Printf("%s %s", r.Method, r.URL.Path)
		fmt.Fprintln(w, "hello from go")
	})

	// AWS_LAMBDA_HTTP_ENDPOINT is typically 0.0.0.0:3000
	ln, err := net.Listen("tcp", os.Getenv("AWS_LAMBDA_HTTP_ENDPOINT"))
	if err != nil {
		log.Fatal(err)
	}

	// the runtime interface client would normally do this, but we exec'd over it
	resp, err := http.Post(
		"http://"+os.Getenv("AWS_LAMBDA_RUNTIME_API")+"/2025-09-01/ready",
		"application/json", strings.NewReader("{}"))
	if err != nil {
		log.Fatal(err)
	}
	resp.Body.Close()

	srv := &http.Server{Handler: mux}

	go func() {
		sig := make(chan os.Signal, 1)
		signal.Notify(sig, syscall.SIGTERM)
		<-sig
		// Lambda gives us one second after SIGTERM before it pulls the plug
		ctx, cancel := context.WithTimeout(context.Background(), 900*time.Millisecond)
		defer cancel()
		srv.Shutdown(ctx)
	}()

	if err := srv.Serve(ln); err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
```

And to build and package it:

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -o server .
zip function.zip index.js server
```

With this, it works! The environment contains exactly two processes, `init` and
`server`, and the Go server is PID 2 with parent 0, which is where Node used
to be. `platform.initReport` was 298ms. `/proc/self/status` says 9.8MB RSS,
and `/proc/meminfo` says 22MB of anonymous memory in the whole VM. The Go
server's `log.Printf` output goes to the CloudWatch stream via stdout, albeit
without the JSON structure that the RIC's patched `console` would give you.
`SIGTERM` arrives at Go directly, Go's `http.Server` closes, and the platform
reports a clean `spinDownReport` 71ms later rather than the `SpinDownTimeout`
my misbehaving Node probe got. 

A weird thing: with this Go implementation, CPU usage (which you're billed for) 
when nothing was running was reported as 56ms per minute. With Node.js, it was 
about 115ms per minute, so Node costs an extra millisecond of CPU per second 
to do nothing. Not sure what's going on here.

## What the platform reports

`maxMemoryUsageMb` in the `invokeSummary` lines sat at 139 for the whole
lifetime of the environment.
It's a high-water mark: 139MB is what Node used to boot and `import()` my
one-line `index.js`, and the number never went back down after the exec even
though the memory did. The [pricing page](https://aws.amazon.com/lambda/pricing/)
says you're charged for the memory **consumed** over time rather than the peak,
but the peak is the only figure you're shown, so I can't confirm from the
telemetry that the saving reaches the bill. So I'm not sure this approach
saves money, but it does let me keep writing Go, so I'm happy. And to be honest
I expect that AWS will launch more runtimes pretty quickly.

[launch]: https://aws.amazon.com/blogs/aws/announcing-aws-lambda-web-functions-for-fast-consistent-web-app-performance-anywhere/
[main-post-ric]: /blog/2026/10/12/some-notes-on-lambda-web-functions.html#inside-the-execution-environment
