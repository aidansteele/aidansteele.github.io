---
layout: post
title: openrolesanywhere - an IAM Roles Anywhere client
date:
  created: 2022-07-14T05:07:52
categories:
  - AWS
---

<!-- more -->

**Update**: AWS now has an [open source implementation][aws-oss] of a Roles
Anywhere `credential_process` provider - and it even supports PKCS#11. I'll 
keep the following project online for historical purposes, but there's not
much need for it.

I just published a proof-of-concept CLI tool named [`openrolesanywhere`][github].
It lets you assume a role in AWS using IAM Roles Anywhere and a private key 
stored in your SSH agent - rather than on-disk as required by the official client.
It implements `AWS4-X509-RSA-SHA256`, `AWS4-X509-ECDSA-SHA256` via a forked
copy of the SigV4 signer in the AWS SDK for Go.

Check out the [repo][github] for more details.

[aws-oss]: https://github.com/aws/rolesanywhere-credential-helper
[github]: https://github.com/aidansteele/openrolesanywhere
