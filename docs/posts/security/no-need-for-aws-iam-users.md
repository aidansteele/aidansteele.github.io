---
layout: post
title: No need for AWS IAM users
date:
  created: 2021-11-06T06:23:52
categories:
  - AWS
---

<!-- more -->

It's long been considered "best practice" to avoid having IAM _users_ in AWS.
Where possible IAM _roles_ are preferable as role session credentials are 
short-lived. As far as I can tell, the only justification for AWS IAM users that 
I hear nowadays is for usage on non-interactive systems outside of AWS (so AWS SSO
won't work), e.g. a Raspberry Pi in your closet.

I created a proof-of-concept project [`cloudkey`][github] to show that even that 
scenario can avoid IAM users. It uses the little-known [`iot:AssumeRoleWithCertificate`][aws-blog]
functionality to avoid that.

Specifically, it uses the "card authentication" slot on a Yubikey to store a TLS
certificate and private key. This slot can be used to sign requests without a PIN
or touch - perfect for the Raspberry Pi use case. By making a `credential_process`
app for it, it works with any AWS SDK or AWS CLI from the last few years.

This could also be made to work with [TPMs][tpm] for deployments where having a 
removeable Yubikey is undesirable.

I'd love to hear from you if you can think of any remaining reasons why IAM users
are still necessary.

[github]: https://github.com/aidansteele/cloudkey
[aws-blog]: https://aws.amazon.com/blogs/security/how-to-eliminate-the-need-for-hardcoded-aws-credentials-in-devices-by-using-the-aws-iot-credentials-provider/
[tpm]: https://en.wikipedia.org/wiki/Trusted_Platform_Module
