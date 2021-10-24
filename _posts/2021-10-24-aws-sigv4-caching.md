---
layout: post
title: AWS SigV4 caching
date: 2021-10-24 16:49:52 +1100
categories: blog
---

Say you find yourself doing silly things with AWS APIs on a lazy Sunday
afternoon. And you are getting the following inexplicable error when using
perfectly valid crendentials:

```xml
<Error>
    <Type>Sender</Type>
    <Code>SignatureDoesNotMatch</Code>
    <Message>The request signature we calculated does not match the signature 
    you provided. Check your AWS Secret Access Key and signing method. Consult 
    the service documentation for details.</Message>
  </Error>
```

The solution might be `sleep()`. Ideally for yourself (the sun is shining and it
_is_ Sunday afternoon), but in your code is also acceptable. Or hang up and
reconnect.

## Why?

There appears to be a credential cache on the AWS services. Specifically, it looks
like:

* The cache timeout is 5 seconds
* It is keyed by access key ID<sup>1</sup> (i.e. `AKIA...` or `ASIA...`)
* Only **invalid** credentials are cached

So you'll only be hit by this issue if you try a [valid key ID, invalid secret key]
pair followed (within 5 seconds) by [same valid key ID, valid secret key].

I suppose it's fair enough, because it doesn't affect legitimate usage and it's 
a cheap way for AWS to avoid spending too much time processing invalid 
credentials - can you imagine all the infinite loops of bad credentials trying 
to hammer their APIs all the time?

<sup>1</sup>: Maybe it's keyed by the entire `Credential=AKIA0123456../20211024/us-east-1/sts/aws4_request`
string, but I'm not going to wait until the stroke of midnight to find out.
