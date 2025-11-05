---
layout: post
title: "Gotcha: always use ARNs for S3 SSE-KMS"
date:
  created: 2024-06-05T01:36:00
categories:
  - AWS
---

<!-- more -->

Imagine you have a scenario represented in the following diagram: 

![diagram](/assets/2024-06-05-diagram.png)

When role 2 in account 2 calls `s3:PutObject` to store an object in bucket 1,
which KMS key do you think is used to encrypt the object? 

If you guessed key 2 (i.e. the one in the same account as the role) you would 
be right - and you would have known more than I did this morning. I assumed it
would be key 1, i.e. the one living in the same account as the bucket. I would
wager a guess that most people would think the same as I did (i.e. that 
unqualified key IDs and aliases are resolved relative to the bucket's account, 
not the caller's account) when they are configuring their bucket's encryption 
configuration.

## Why is this a problem?

This behaviour can cause problems in two ways. 

The first is the more likely scenario: key 2 doesn't exist. Then role 2's 
attempt to write objects will fail with an error message about a KMS key with 
ARN `arn:aws:kms:region:22222222:alias/my-key` not existing. At least that
"fails fast" and can be resolved.

The second is described at the start of this post: the object will be successfully
stored and encrypted with key 2. Now if any principals in account 1 try to read
the object they will fail with KMS decryption errors, even if they have permission
to decrypt using key 1 -- that will cause a lot of confusion down the track, 
especially if roles from both accounts write to the bucket: some objects will be 
encrypted with key 1 and some encrypted with key 2. The only way to fix those is
to re-upload the objects.

## What can be done to prevent it?

Always use a fully-qualified ARN (either a key ID or key alias is fine) and you
won't have this problem. AWS already tries to nudge users towards this safe 
default: the web console will only allow you to specify an ARN. I suspect they won't
change the API because of their commendable commitment to backwards compatibility.

## Do other AWS services have this issue?

There are a lot of services that allow a) cross-account access and b) encryption
using customer-managed KMS keys. I don't have the time to check them all, but I
did check DynamoDB and Secrets Manager.

DynamoDB doesn't have this problem because when a value like `alias/my-key` is
provided to the `UpdateTable` API, it is resolved to a fully-qualified key ARN
and stored as such. 

Secrets Manager likewise doesn't have this problem. It doesn't take the DynamoDB
approach of resolving to a fully-qualified ARN, but it will fail fast-ish. 
Cross-account _reads_ will get the error message `Access to KMS is not allowed`.
Cross-account _writes_ will get `You must specify a KMS key ARN to update the secret from a different AWS account.`
It would be nice if the first error message was as helpful as the second error
message, but now I'm just being picky.

## Is this a security issue?

I don't think so. The closest I can come is this really contrived scenario:

* Key 2's key policy is changed to allow any AWS account to call `kms:Decrypt`.
* Role 2 downloads and re-uploads every object in bucket 1, encrypted with key 2.
* Now the administrator of account 2 gets a sneaky audit trail of everyone who
  reads objects from bucket 1. The administrator of account 1 might not like that.
