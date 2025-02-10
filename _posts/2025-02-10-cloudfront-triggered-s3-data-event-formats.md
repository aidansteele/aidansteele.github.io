---
layout: post
title: CloudFront-triggered S3 data event formats
date: 2025-02-10 16:32:00 +1100
categories: blog
---

There are several ways that CloudFront can be configured with an S3 origin. There
are functionality differences between them, but the focus in this blog post is
how activity is represented in CloudTrail, specifically the differences in S3
data-level events for each CloudFront option. Those options in CloudFront are 
(in decreasing order of desirability):

1. S3 origin with an Origin Access Control (OAC) configuration. OACs were launched
   in 2022 and support all AWS regions, SSE-KMS-encrypted objects and PUT/DELETE
   HTTP verbs. 
2. S3 origin with an Origin Access Identity (OAI) configuration. OAIs were 
   launched in 2009[1] and prior to OACs were the only way to serve public from
   an S3 bucket without also making the S3 bucket directly accessible to the 
   world.
3. S3 origin with public access. This means making your bucket accessible to the
   world and hoping no one finds your bucket name and bypasses your CDN/firewall.
4. Custom origin pointed at an S3 bucket with static website hosting enabled.

The format of `s3:GetObject` events in CloudTrail will depend on which one of
these options you choose. I couldn't find any examples of these events online,
so I tried out each option and published them in [**this gist**][gist]. I 
"normalised" each event to reduce spurious differences - the structure is what 
I care about.

A summary of the differences that I found interesting:

a) When using an OAC, the `sourceIPAddress` and `userAgent` are both rewritten
to `cloudfront.amazonaws.com`. In all other scenarios the source IP address
is a random CloudFront public IP and the user-agent is `[Amazon CloudFront]`.

b) The `userIdentity` field looks like this for OAC vs OAI vs public access:

```json5
// OAC
{
  "invokedBy": "cloudfront.amazonaws.com",
  "type": "AWSService"
}

// OAI
{
  "accountId": "CloudFront",
  "principalId": "AIDAIWBU3NBABM5FLVT5E",
  "type": "AWSAccount"
}

// Public
{
  "accountId": "anonymous",
  "principalId": "",
  "type": "AWSAccount"
}
```

The _format_ of the event makes most sense when using OAC, but it feels like a
slight regression compared to using an OAI: there is no way to determine from
CloudTrail _which_ OAC was used to access the bucket[2]. Feature request for Amazon:
it would be great if the ARN of the OAC appeared here, ideally in the new-ish
`userIdentity.inScopeOf.sourceArn` field. 

c) When using an OAC, the `tlsDetails` field is omitted entirely. We probably
don't need this level of implementation detail anyway, but we can still confirm
that HTTPS is used thanks to the `additionalEventData.CipherSuite` field.

[1]: I learned this thanks to [this][timeline] very detailed timeline.

[2]: You can determine which OAI was used by pasting the `userIdentity.principalId`
field (i.e. the one beginning `AIDA...`) into [my website][awsid].

[gist]: https://gist.github.com/aidansteele/31d6055de2ec98e31807fdf96511b4c6
[timeline]: https://hidekazu-konishi.com/entry/aws_history_and_timeline_amazon_s3.html
[awsid]: https://awsid.dev.ak2.au/
