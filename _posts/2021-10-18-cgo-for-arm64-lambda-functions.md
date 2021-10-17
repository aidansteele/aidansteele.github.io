---
layout: post
title: cgo for ARM64 Lambda Functions
date: 2021-10-18 10:05:52 +1100
categories: blog
---

In my post [_Graviton2: ARM comes to Lambda_][first-post] I showed that it is
very easy to cross-compile Go code to run on ARM64 AWS Lambda functions. That's
true as long as your code is 100% Go - as soon as there's any C code involved
it feels impossible. I mean, who wants to deal with this error message?

![cgo error message](/assets/2021-10-18-error-message.png)

It turns out there's a solution: to use [Zig][ziglang] to compile and link your
C code. Zig is an extremely interesting new programming lanugage that seeks to
replace C. It also happens to be able to compile C via `zig cc`. It can also
_cross_-compile C. Check out this amazing [blog post][zig-blog] by its creator.
Anyway, here's how to do it:

## SQLite and Go on ARM64 Lambda functions via Zig

Here's a useless Lambda function:

```go
package main

import (
	"context"
	"crawshaw.io/sqlite/sqlitex"
	"encoding/json"
	"github.com/aws/aws-lambda-go/lambda"
)

var dbpool *sqlitex.Pool

func main() {
	dbpool, _ = sqlitex.Open("file:memory:?mode=memory", 0, 1)
	lambda.Start(handle)
}

func handle(ctx context.Context, input json.RawMessage) (string, error) {
	conn := dbpool.Get(ctx)
	defer dbpool.Put(conn)

	// please excuse my complete lack of error handling
	stmt, _, _ := conn.PrepareTransient("SELECT 123")
	defer stmt.Finalize()

	stmt.Step()
	return stmt.ColumnText(0), nil
}
```

And here's how you can compile it for ARM64 (and x86_64) from your laptop:

```bash
# build.sh
set -eux
export GOOS=linux
export CGO_ENABLED=1
export CC=$(pwd)/zcc.sh
export CXX=$(pwd)/zxx.sh

GOARCH=arm64 \
ZTARGET=aarch64-linux-musl \
go build -ldflags="-linkmode external" -o arm64/bootstrap

GOARCH=amd64 \
ZTARGET=x86_64-linux-musl \
go build -ldflags="-linkmode external" -o amd64/bootstrap
```

Here's what those `zcc.sh` and `zxx.sh` files should look like:

```bash
# zcc.sh
#!/bin/sh
set -eu
export ZIG_SYSTEM_LINKER_HACK=1
export ZIG_LOCAL_CACHE_DIR="$HOME/.zigcache/"
zig cc -target $ZTARGET "$@"

# zxx.sh
#!/bin/sh
set -eu
export ZIG_SYSTEM_LINKER_HACK=1
export ZIG_LOCAL_CACHE_DIR="$HOME/.zigcache/"
zig c++ -target $ZTARGET "$@"
```

Finally, for completeness, a potential CloudFormation template for your functions:

```yaml
Transform: AWS::Serverless-2016-10-31

Resources:
  Arm64:
    Type: AWS::Serverless::Function
    Properties:
      Handler: hello
      CodeUri: ./arm64/bootstrap
      Runtime: provided.al2
      Architectures: [arm64]

  Amd64:
    Type: AWS::Serverless::Function
    Properties:
      Handler: hello
      CodeUri: ./amd64/bootstrap
      Runtime: provided.al2
      Architectures: [x86_64]
```


[first-post]: /blog/2021/09/29/graviton2-arm-comes-to-lambda.html
[ziglang]: https://ziglang.org/
[zig-blog]: https://andrewkelley.me/post/zig-cc-powerful-drop-in-replacement-gcc-clang.html
