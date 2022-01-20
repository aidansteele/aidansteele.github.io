---
layout: post
title: "AWS GWLB: Deep Packet Manipulation"
date: 2022-01-20 11:53:52 +1100
categories: blog
---

AWS [introduced Gateway Load Balancers][intro-blog] back in November 2020. A
reasonably accurate tl;dr would be that they are like having highly available, 
auto-scaling NAT instances. That intro blog post will explain them better than
I can.

The blog post mentions a dozen AWS partners that implement various flavours of
firewalls, deep packet inspection, DDoS protection, etc. It's all useful and
serves a genuine need, but not very exciting from a developer perspective. 

There's been a real dearth of community blog posts about it in the subsequent 
years. There's the [GeneveProxy][sentia] post by Luc van Donkersgoed, which does
a **really** great job of explaining how the GWLB works and how to build a sample
app for it, but that's about it. I suspect it's because going beyond a simple
packet-by-packet model explodes in complexity. If you are more interested in the
demos than why it's hard, you can skip to the bottom. Otherwise, I'll try explain:

## The complexity

GWLBs aren't hard themselves, look at this diagram (from Amazon's blog post):

![amazon diagram](/assets/2022-01-20-aws-diagram.png)

It's inspecting and modifying network traffic in general that is extremely 
difficult. Especially non-trivial modifications.  Take the following diagram as 
an example. This is just one packet in a flow of packets between an EC2 
instance and the Internet when `curl https://google.com` is run.

![packet diagram](/assets/2022-01-20-geneve-packet-http2.png)

You can think of this packet as having many layers. Each layer "wraps" the
layer below it. The bottom six layers were sent by the EC2 instance. The top
three layers are GWLB-specific. They identify which VPC endpoint (e.g. customer)
the packet came from and which "flow" of packets this particular packet belongs to.

Say we want to change all web requests to google.com to have the `User-Agent`
request header instead be lower-case, e.g. `user-agent`. This would require us to
parse the formats for:

* The inner IPv4 layer, to identify is this a TCP packet
* The TCP layer, to identify if the destination port is 80 or 443
* The TLS layer, to (magically, for now) decrypt the payload
* The HTTP/2 layer, to inspect the multiplexed streams within
* The frames in each HTTP/2 stream, to identify if they are a `HEADERS` frame.
* The headers in the HTTP/2 frame, to see if the `User-Agent` header is present.

Finally we would have to edit the packet in memory at the right offset to change
`U` to `u` and `A` to `a`, correct the checksums at every layer of the packet
and re-encrypt the TLS payload. That's a lot of work.

And that's a trivial change: the packet length hasn't changed. Imagine if
wanted to insert a few additional headers in that request. Maybe that would
push the packet length over the typical 1500 byte limit for packets on the
Internet. That increases the amount of work needed by orders of magnitude: now
we need to reimplement the TCP state machine, because we'll now need two packets.
And those packets each need sequence numbers. But the original EC2 instance will
get a response from Google for sequence numbers it didn't expect, so the
connection will fail. So what we need to do is instead _terminate_ the TCP
connection at the GWLB appliance and open a _new_ connection to Google from the
GWLB appliance. The app will need to juggle these two TCP connections and pass
the underlying data to and from Google and the EC2 instance, all while keeping
the two connection's different states in sync.

That's so much work that it's no wonder that even after more than a year, only 
massive well-funded vendors have  implemented this capability. And even then, it 
looks like they're limited to either read-only inspection or dropping suspicious 
packets.

## A solution

I've come up with a handful of demo applications, only made possible thanks to
some fantastic open source software. Specifically:

* [`inet.af/netstack`](https://pkg.go.dev/inet.af/netstack): a reimplementation
  of the entire Linux TCP/IP stack in Go, extracted from the gVisor project.

* [`github.com/google/gopacket`](https://pkg.go.dev/github.com/google/gopacket)
  to extract and parse the Geneve, IP, TCP, UDP, etc layers from the raw packets
  delivered by the GWLB.

* [`httputil`](https://pkg.go.dev/net/http/httputil) in the Go stdlib, to
  reverse-proxy HTTP and HTTPS traffic and  parse flows into individual request
  and response objects.

* [`github.com/aws/aws-sdk-go`](https://pkg.go.dev/github.com/aws/aws-sdk-go) to
  use AWS KMS asymmetric keys for the root certificate authority that can be
  installed on EC2 instances for transparent TLS decryption - without having to
  manage a highly-sensitive private key.

* [`rogchap.com/v8go`](https://pkg.go.dev/rogchap.com/v8go) to embed the V8
  JavaScript engine into Go, so that we can write scripts to modify traffic
  in JS, which is more familiar than Go to many developers.

## Example use cases

These are really just intended to demonstrate that anything is possible in the
world of software-defined networking. Please ping me on [Twitter][twit] with any
cool ideas you have. Or any enhancements to the following ideas.

* [`lambda_acceptor/lambda_acceptor.go`](https://github.com/aidansteele/flowdog/blob/main/examples/examples/lambda_acceptor/lambda_acceptor.go)
  takes the idea of [AWS API Gateway Lambda authorizers][apigw-auth] and applies
  it to VPC flows. At the start of every new connection, a Lambda function is
  invoked and returns a decision about whether to allow or drop the connection.
  It's like security groups 2.0. Input/output looks like this:

  ![authorizer-io](/assets/2022-01-20-authorizer.png)

* [`flowdogshark/flowdogshark.go`](https://github.com/aidansteele/flowdog/blob/main/examples/examples/flowdogshark/flowdogshark.go) is an
  [`extcap`][extcap] plugin for Wireshark that allows you to live-attach 
  Wireshark to flowdog and capture traffic flowing through your VPC. Given that
  flowdog does TLS interception (see later section in README), it can even use 
  Wireshark's support for decoding TLS. Here's an example of intercepting the
  Amazon SSM agent:

  ![wireshark demo](/assets/2022-01-20-wireshark-demo.png)

* [`account_id_emf/account_id_emf.go`](https://github.com/aidansteele/flowdog/blob/main/examples/examples/account_id_emf/account_id_emf.go)
  is an example of scanning all AWS API calls made within the VPC for SigV4 auth
  headers, [extracting the AWS account ID][extract-acct-id] and emitting it to
  CloudWatch via specially-formatted logs that are turned into metrics. This could
  be used to alert on newly-seen account IDs: a potential indicator of a compromised
  instance.

* [`upsidedown/upsidedown.go`](https://github.com/aidansteele/flowdog/blob/main/examples/examples/upsidedown/upsidedown.go) is an 
  implementation of the classic [Upside-Down-Ternet][upsidedown]. It blurs and 
  rotates every image 180º when browsing the net.

  ![upside down](/assets/2022-01-20-upside-down.png)

* [`sts_rickroll/sts_rickroll.go`](https://github.com/aidansteele/flowdog/blob/main/examples/examples/sts_rickroll/sts_rickroll.go) is
  another silly example. Here we are modifying the response of the AWS API call
  for `aws sts get-caller-identity` to return something unexpected. You could
  equally use the same logic to return your favourite video on every seventh
  object downloaded through an S3 VPC gateway. 

  ![sts-rickroll](/assets/2022-01-20-sts-rickroll.png)

* [`gwlb/websocket.go`](https://github.com/aidansteele/flowdog/blob/main/examples/gwlb/websocket.go) is not an example, but I got lazy.
  [Nick Frichette][nickf] had the great suggestion of intercepting the [SSM agent][agent]
  for shenanigans. This code will detect websockets and parse messages, but right
  now only passes them back and forth. Soon™.

* [`cloudfront_functions/rick.js`](https://github.com/aidansteele/flowdog/blob/main/examples/examples/cloudfront_functions/rick.js) is
  an example of how the [CloudFront Functions][cff-model] event model can be
  applied to rewriting HTTP(S) requests inside a VPC. In this particular example,
  we're ensuring that any [AWS Workspaces][workspaces] users visiting YouTube
  can only watch one particular video. Code:

```javascript
function onRequest(event) {
    const r = event.request;
    if (r.headers.host.value !== "www.youtube.com") {
        return r;
    }

    const onlyVideoOnYoutube = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
    const referer = r.headers.referer;
    if (referer && referer.value === onlyVideoOnYoutube) {
        return r;
    }

    if (r.uri === "/watch" && r.querystring.v.value === "dQw4w9WgXcQ") {
        return r;
    }

    return {
        statusCode: 302,
        statusDescription: 'Found',
        headers: {
            location: { value: onlyVideoOnYoutube }
        }
    };
}
```

## Bonus: TLS 

We haven't broken TLS. For this app, we create a custom root certificate authority 
and add it to the trust store on our EC2 instances. Rather than deal in sensitive 
private key material, we use  AWS [KMS' support for asymmetric keys][kms] for our 
private key. [`generate.go`](/kmssigner/generate/generate.go) creates a certificate 
using that key. That certificate is then stored and trusted on the OS (e.g. in 
Amazon Linux 2 you would run `cat $CERT >> /usr/share/pki/ca-trust-source/anchors/lol.pem && update-ca-trust`)

Rather than invoking KMS on every TLS connection, on launch this app creates an
ephemeral key pair and certificate in memory, asks KMS to sign it and then uses
that as an intermediate certificate authority. This means we can have fast TLS
de/re-encryption with no stored secrets.

When Wireshark is attached, flowdog can stream TLS key logs in [NSS Key Log Format][klf].
This allows the Wireshark user to view all decrypted TLS traffic without giving
away either the KMS private key (impossible) or intermediate CA private key (very
unwise).

[intro-blog]: https://aws.amazon.com/blogs/aws/introducing-aws-gateway-load-balancer-easy-deployment-scalability-and-high-availability-for-partner-appliances/
[sentia]: https://www.sentiatechblog.com/geneveproxy-an-aws-gateway-load-balancer-reference-application
