---
layout: post
title: A role for all your EC2 instances
date: 2023-02-21 09:12:52 +1100
categories: blog
---

**tl;dr: You can now pass an IAM role to every EC2 instance in your account + region.**

On Feb 17th 2023, AWS Systems Manager released [Default Host Management Configuration][dhmc].
This is a way to use Systems Manager on all your EC2 instances: they don't need 
`ssm:*` permissions in their instance profiles, nor do they even need an instance
profile at all.

So how does it work?

1. You create a role `MyCoolRole` assumable by `ssm.amazonaws.com`
2. You configure DHMC by calling the following:
   ```
   aws ssm update-service-setting \
     --setting-id arn:aws:ssm:${AWS_REGION}:${AWS_ACCOUNT_ID}:servicesetting/ssm/managed-instance/default-ec2-instance-management-role \
     --setting-value MyCoolRole
   ```
3. The SSM agent on your EC2 instances can now retrieve credentials for `MyCoolRole`.

What's interesting to note is that this role can have *any* permissions, it's not
scoped down just to SSM agent-relevant permissions. I created a proof-of-concept
[`credential_process` credential provider][cred-process] called [awsaccountcreds][github].

To try it out, create an EC2 instance without an associated instance profile,
install `awsaccountcreds` and write the following to `~/.aws/config`:

```
[default]
credential_process = /home/ec2-user/awsaccountcreds # or wherever you placed the executable
```

Now you can run something in the AWS CLI, like `aws sts get-caller-identity` or 
(if you granted the DHMC role S3 access) `aws s3 ls`.

## How it works, sequence diagram-style

See the following sequence diagram. The CLI retrieves (from the instance metadata
service) "instance identity" SigV4 credentials. Prior to DHMC, these were only used for
[EC2 Instance Connect][ec2ic] (as far as I know). Calling `sts:GetCallerIdentity`
with these credentials reveal they have an interesting ARN format: `arn:aws:sts::607481581596:assumed-role/aws:ec2-instance/i-0ab9ac31d8ff41296`.

Next an RSA keypair is generated. The key pair's public key is sent to SSM using
the undocumented `ssm:RegisterManagedInstance` API. This API call is signed using
the above credentials (`C_0` in the diagram).

Finally, `ssm:RequestManagedInstanceRoleToken` (also undocumented) is invoked.
This is also signed using `C_0` credentials and has an additional `SSM-AsymmetricKeyAuthorization`
request header. This request header is an RSA signature over the `Authorization`
SigV4 header. This API returns credentials (`C_1` in the diagram) for a role 
session for the DHMC role with the instance ID as the role session name.

It seems only one RSA keypair can be registered for a given instance ID. This 
keypair can then be used to retrieve credentials multiple times. I haven't yet 
looked into how the RSA keypair gets refreshed, but it seems to be a thing (the
API has a boolean `UpdateKeyPair` response field)

![sequence diagram](/assets/2023-02-21-sequence-diagram.png)

## Risks

I reported the potential for passing an over-privileged role to the AWS security
team, and they described it as working as designed. Which is correct, and this
probably falls on the customer side of the shared responsibility model. (Though
I'm not sure why Systems Manager doesn't pass `PolicyArns=[arn:aws:iam::aws:policy/AmazonSSMManagedEC2InstanceDefaultPolicy]` 
when calling `sts:AssumeRole`) But the risk remains: anyone with `ssm:UpdateServiceSetting` 
and `iam:PassRole` can affect every EC2 instance in a single API call. And in 
my experience, these permissions are typically granted to developers.

The other risk is that even though this is described as a solution for managing
instances that don't already have SSM privileges, it affects those instances
too. Because the SSM agent tries the instance profile first (and only falls back
to DHMC if the instance profile fails), it means that those instances remain
"unregistered" and `ssm:RegisterManagedInstance` will succeed for a process
running on the machine.

## Thanks

Thanks to [Ian Mckay][ian], [Nick Frichette][nick] and [Christophe Tafani-Dereeper][christophe]
for sanity-checking this. Also big thanks to Ben Bridts, who [pointed out][ben-tweet]
that Systems Manager couldn't just pass the `AmazonSSMManagedEC2InstanceDefaultPolicy`
managed policy as a session policy, because that would preclude the S3 and
KMS privileges needed for other parts of Systems Manager functionality. Also
thanks to the Cloud Security Forum folks whose discussion of this functionality
prompted me to do the research.

[dhmc]: https://docs.aws.amazon.com/systems-manager/latest/userguide/managed-instances-default-host-management.html
[cred-process]: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sourcing-external.html
[github]: https://github.com/aidansteele/awsaccountcreds
[ec2ic]: https://github.com/aws/aws-ec2-instance-connect-config/blob/32d7656adbf5f4b59f9aacd519b545dcedec7fe1/src/bin/eic_harvest_hostkeys#L119
[ian]: https://twitter.com/iann0036
[nick]: https://twitter.com/Frichette_n
[christophe]: https://twitter.com/christophetd
[ben-tweet]: https://twitter.com/benbridts/status/1627844227399917569
