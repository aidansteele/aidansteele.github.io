---
layout: post
title: openrolesanywhere - an IAM Roles Anywhere client
date: 2022-07-14 15:07:52 +1000
categories: blog
---

I just published a proof-of-concept CLI tool named [`openrolesanywhere`][github].
It lets you assume a role in AWS using IAM Roles Anywhere and a private key 
stored in your SSH agent - rather than on-disk as required by the official client.
It implements `AWS4-X509-RSA-SHA256`, `AWS4-X509-ECDSA-SHA256` via a forked
copy of the SigV4 signer in the AWS SDK for Go.

Check out the [repo][github] for more details.

[github]: https://github.com/aidansteele/openrolesanywhere
