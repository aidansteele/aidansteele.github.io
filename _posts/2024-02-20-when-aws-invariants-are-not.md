---
layout: post
title: When AWS invariants aren't [invariant]
date: 2024-02-20 11:21:00 +1100
categories: blog
---

## tl;dr

Search CloudTrail for instances of `AssumeRole` with 
`additionalEventData.explicitTrustGrant == false`. These will yield results
for role assumptions that **aren't** permitted by the trust policy, i.e. the
ones that are going to surprise you - and violate your invariants like "role 
session names will always be an employee's email address".

## Not quite invariant

Arkadiy Tetelman recently published a very interesting [blog post][arkadiy] on
detecting manual actions undertaken by humans in his AWS environment. It's worth
reading: if you haven't already, read it first and then come back here.

I want to draw attention to two things he said, because they recently caught me
out and I suspect they might be surprising to others. This is the first:

> * The only way that employees can access AWS is through Okta / AssumeRoleWithSAML. 
>   There are no other mechanisms for an employee to get access to AWS (zero 
>   IAM users, etc)
> 
> * When someone assumes an employee role, Okta is configured to set the AWS 
>   role session name to be the employee email address
>
> The above two conditions are an _invariant_ for employee access to AWS.

The second is this:

> Also until [very recently][aws-blog] every role was always allowed to assume 
> itself, which similarly allowed you to change your own role session name.

The AWS blog that Arkadiy links to actually briefly mentions that the implicit
allowed self-assumption behaviour is **still present** for some roles - and it's
not easy to find out which roles that applies to. This is what caught me out: I
had some roles that still had the grandfathered-in implicit self-assumption allowed
and I had no idea. 

The AWS blog shares an AWS Athena query that can be used to identify instances of
role self-assumption, but this isn't helpful in a large enterprise: there will 
be many false positives, because it will also return instances of self-assumption
that is permitted by _explicit_ statements in the role's trust policy. We only
want to identify roles that are still relying on the _implicit_ behaviour.

It turns out that it is actually possible to identify the implicit behaviour, but
I only stumbled across it by accident when reviewing CloudTrail logs. It doesn't
appear to be documented by AWS on the Internet - there's only this copy of an 
email pasted into a [GitHub discussion][github] and it doesn't even appear on 
Google.

![empty google results](/assets/2024-02-20-google-no-results.png)

## Email

In the interest of searchability, I've reproduced the email from Amazon here:

> We contacted you previously regarding an AWS Identity and Access Management
> (IAM) change delivered on September 21, 2022 that updated an aspect of how role
> trust policy evaluation behaves when a role assumes itself. With this change,
> role assumption always requires an explicit role trust policy grant. At that
> time, we identified one or more roles in this account relying on implicit trust
> when the role assumes itself. These roles were placed on a temporary allow list
> to prevent AssumeRole calls from being denied due to the new trust policy
> evaluation behavior. We advised you to make any necessary changes to your
> existing processes, code, or configurations to prepare for elimination of the
> implicit trust behavior. For more information about this behavior change in your
> account, please review additional details in the blog post "Announcing an Update
> to IAM Role Trust Policy Behavior" [1].
> 
> On February 3, 2023, we announced that starting June 30, 2023, all roles,
> regardless of allow list status, that attempt to assume themselves will fail
> with an access denied error unless the role trust policy explicitly grants the
> permission and the conditions and actions are satisfied.
> 
> We are contacting you again to announce that rather than enforcing an explicit
> trust grant for all roles regardless of allow list status starting June 30,
> 2023, we will instead automatically remove roles from the allow list based on
> observed role assumption behavior. Roles on the allow list that we observe
> either not performing role self-assumption or whose trust policy grants explicit
> trust with every role assumption over the previous 90 days or more are
> candidates for removal. A role that performs self-assumption without granting
> explicit trust at least once over the previous 90 days will be retained on the
> allow list to give you additional time to make the necessary code or
> configuration changes. As we announced on December 20, 2022, you can verify
> whether a specific role self-assumption call by an allow-listed role grants
> explicit trust by reviewing the corresponding CloudTrail entry and observing a
> value of “true” for the “explicitTrustGrant” flag.
> 
> Automatic removal of candidate roles from the allow list that match the criteria
> defined above begins on June 30, 2023. You may choose to remove a role from the
> allow list prior to its identification as a removal candidate if its role
> assumption behavior matches your use case expectations. For assistance with
> removing such roles from the allow list, please contact AWS Support [2].
> 
> Once a role is removed from the allow list, its role assumption calls will
> always require an explicit trust grant.

[arkadiy]: https://arkadiyt.com/2024/02/18/detecting-manual-aws-actions-an-update/
[aws-blog]: https://aws.amazon.com/blogs/security/announcing-an-update-to-iam-role-trust-policy-behavior/
[github]: https://github.com/orgs/gruntwork-io/discussions/748