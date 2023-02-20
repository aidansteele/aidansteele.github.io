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

[dhmc]: https://docs.aws.amazon.com/systems-manager/latest/userguide/managed-instances-default-host-management.html
[cred-process]: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sourcing-external.html
[github]: https://github.com/aidansteele/awsaccountcreds
