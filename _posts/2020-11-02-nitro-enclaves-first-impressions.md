---
layout: post
title:  Nitro Enclaves - First Impressions
date:   2020-11-02 14:31:52 +1100
categories: blog
---

At the end of October, AWS [released][nitro-blog] Nitro Enclaves. My mental model of these is essentially a *secure* virtual machine within a virtual machine - the outer VM being an EC2 instance. The *secure* qualifier is to distinguish that the inner VM has many restrictions: by default it has no network access, no persistent disk, no access to processes running on the host and crucially, vice-versa: the host likewise doesn't have access to resources inside the enclave. All communication instead happens over [`vsock`][vsock] sockets.

This is all pretty cool, but what really piqued my interest is the integrations that enclaves have with AWS KMS cryptography and AWS-certified attestations of enclave identity and integrity. In other words, you can write AWS [KMS key policies][kms-policies] that ensure that only signed and unmodified code can decrypt or encrypt particular data. It also means that code running in an enclave can *attest* (prove) to third parties that it is running on a particular EC2 instance and that the code has not been tampered with.

## Shenanigans for self-education

The way I usually learn new things is by using them, changing them, breaking them, etc. In the case of Nitro Enclaves, the first thing I did was write an Enclave that allowed me to SSH into it over the `vsock` socket (instead of a regular TCP socket on port 22) as per a [silly tweet][tweet]:

![screenshot](/assets/2020-11-02-ssh-enclave.jpeg)

This was fun, but pretty pointless. I was much more interested in the cryptographic attestations that the Nitro hypervisor would provide on behalf on enclaves. The [attestation process][attestation-process] is documented in great detail on GitHub. In fact, a good deal of the user-facing implementation details of Nitro Enclaves are open source and provided on GitHub. This is really great work by AWS.

The attestation process works by sending some optional data (a public key, a nonce and arbitrary user data) to the hypervisor via the `/dev/nsm` special file and getting a CBOR-encoded document back. The hairy implementation details of this are abstracted by the helpful [`nsm_get_attestation_doc`][nsm-get-doc-rust] function in the NSM (Nitro Secure Module) library. The library is written in Rust, but consumable from almost any language thanks to it exporting a C ABI.

This attestation document includes a handful of fields in one form or another. These are:

* The EC2 instance ID
* The enclave ID
* The SHA-384 digest of the Nitro enclave `.eif` file
* The optional user-provided public key, nonce and user data
* A chain of X.509 certificates from this enclave all the way to the global Nitro root

The document itself is signed by the leaf certificate, which is in turn signed by the first intermediary, etc until you reach the global root Nitro certificate. That root certificate is [documented][root-cert-doc] by AWS. Hell, here it is:

```
-----BEGIN CERTIFICATE-----
MIICETCCAZagAwIBAgIRAPkxdWgbkK/hHUbMtOTn+FYwCgYIKoZIzj0EAwMwSTEL
MAkGA1UEBhMCVVMxDzANBgNVBAoMBkFtYXpvbjEMMAoGA1UECwwDQVdTMRswGQYD
VQQDDBJhd3Mubml0cm8tZW5jbGF2ZXMwHhcNMTkxMDI4MTMyODA1WhcNNDkxMDI4
MTQyODA1WjBJMQswCQYDVQQGEwJVUzEPMA0GA1UECgwGQW1hem9uMQwwCgYDVQQL
DANBV1MxGzAZBgNVBAMMEmF3cy5uaXRyby1lbmNsYXZlczB2MBAGByqGSM49AgEG
BSuBBAAiA2IABPwCVOumCMHzaHDimtqQvkY4MpJzbolL//Zy2YlES1BR5TSksfbb
48C8WBoyt7F2Bw7eEtaaP+ohG2bnUs990d0JX28TcPQXCEPZ3BABIeTPYwEoCWZE
h8l5YoQwTcU/9KNCMEAwDwYDVR0TAQH/BAUwAwEB/zAdBgNVHQ4EFgQUkCW1DdkF
R+eWw5b6cp3PmanfS5YwDgYDVR0PAQH/BAQDAgGGMAoGCCqGSM49BAMDA2kAMGYC
MQCjfy+Rocm9Xue4YnwWmNJVA44fA0P5W2OpYow9OYCVRaEevL8uO1XYru5xtMPW
rfMCMQCi85sWBbJwKKXdS6BptQFuZbT73o/gBh1qUxl/nNr12UO8Yfwr6wPLb+6N
IwLz3/Y=
-----END CERTIFICATE-----
```

This means that code in an enclave can request a signed copy of any arbitrary data, share it with the outside world and **prove** that it came from an untampered app in a specific Enclave.

## What can we do with that proof?

There are lots of interesting things you can do when you can **prove** who you are and that it was **you** who authored some data. I decided that I would create a service that would vend AWS IAM role session credentials to code running in enclaves. This might actually be useful, because for the time being AWS doesn't provide a native way to assign a role to an enclave. Here's a reasonably detailed sequence diagram:

![screenshot](/assets/2020-11-02-sequence-diagram.png)

For roles that you want to be assumable by enclaves, you would then have a trust policy that looks something like this:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowIamUserAssumeRole",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/idp-role"
      },
      "Condition": {
        "StringLike": {
          "aws:RequestTag/enclave:enclave-id": "*",
          "aws:RequestTag/enclave:instance-id": "*",
          "aws:RequestTag/enclave:account-id": "*",
          "aws:RequestTag/enclave:instance-role-arn": "*"
        }
      }
    },
    {
      "Sid": "AllowPassSessionTagsAndTransitive",
      "Effect": "Allow",
      "Action": "sts:TagSession",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:role/idp-role"
      },
      "Condition": {
        "StringLike": {
          "aws:RequestTag/enclave:enclave-id": "*",
          "aws:RequestTag/enclave:instance-id": "*"
        },
        "StringEquals": {
          "aws:RequestTag/enclave:account-id": "123456789012",
          "aws:RequestTag/enclave:instance-role-arn": "arn:aws:iam::123456789012:role/instance-role"
        }
      }
    }
  ]
}
```

I've put a [steaming pile of code][code] on GitHub - please don't use it. It probably has a line-to-bug ratio of 1:1.

[nitro-blog]: https://aws.amazon.com/blogs/aws/aws-nitro-enclaves-isolated-ec2-environments-to-process-confidential-data/

[vsock]: https://man7.org/linux/man-pages/man7/vsock.7.html
[kms-policies]: https://docs.aws.amazon.com/enclaves/latest/user/kms.html
[tweet]: https://twitter.com/__steele/status/1321696473919074304
[attestation-process]: https://github.com/aws/aws-nitro-enclaves-nsm-api/blob/main/docs/attestation_process.md
[nsm-get-doc-rust]: https://github.com/aws/aws-nitro-enclaves-nsm-api/blob/bf5c9f2edb04ede2f5bbe1cb930d8d7c795bea8b/nsm-lib/src/lib.rs#L218
[root-cert-doc]: https://docs.aws.amazon.com/enclaves/latest/user/verify-root.html#validation-process
[code]: https://github.com/aidansteele/freedumb

