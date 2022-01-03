---
layout: post
title: Shared VPCs are underrated
date: 2022-01-03 09:44:52 +1100
categories: blog
---

AWS [launched VPC sharing][launch-blog] in January 2019, two years ago. It feels
to me that there hasn't been much chatter about it since then. Which is a shame,
because I suspect they are quite useful. I'm going to focus on cost and security.

Recommended practice nowadays is to have a "multi-account strategy" in AWS. You
typically have an account per [app, environment]. So if you have three apps and
two environments (e.g. dev and prod) that would be at least six AWS accounts.
Lets also assume that you want to maintain high availability, so you have those
apps deployed across three availability zones. And lets assume that the apps
are deployed in private subnets (i.e. without access to an Internet Gateway) to
appease auditors.

## Cost

With a VPC per AWS account, you have a fixed monthly cost of $250+ per month
per app - see the boring details below for a rationale if you care. I've found
this to have a real chilling effect on people's motivation to spin up new
accounts -- and therefore new apps. You might say that's silly, but it's real
and it has a real (negative, IMO) impact on system architecture.

**Or** you can use VPC sharing and that $250+/month is fixed and doesn't
scale with your number of applications. This means you free up your developers
from the silly mental burden of "does this warrant the cost?" questions that
are a waste of time.

## Security

I think VPC sharing can have a significant positive impact on cloud security.
Take the following [Twitter exchange][tweets] between Houston Hopkins and Nick
Frichette. 

![tweets](/assets/2022-01-03-tweets.png)

They're both right. AWS gives us all these tools to lock things down _but_ they're
almost never used in practice. Think about it: in a VPC-per-account world, how 
are you meant to use the `aws:SourceVpc` IAM policy condition? You can't apply
it an an org or OU level via service control policies (SCPs) as every account 
has different VPC IDs. Same with the `aws:SourceVpce` condition. You _could_ 
have a standard IAM [permission boundary][boundary] in every account, but then 
it's on your developers to use that boundary on every role in those accounts - 
likely to get pushback.

But what if our org architecture looked like this?

![org diagram](/assets/2022-01-03-org-diagram.png)

Then we could apply an SCP to the prod OU that looks something like:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DenyFromOutsideVpcUsingEndpoints",
            "Effect": "Deny",
            "Action": "*",
            "Resource": "*",
            "Condition": {
                "Bool": {
                    "aws:ViaAWSService": "false"
                },
                "Null": {
                    "aws:SourceIp": "true"
                },
                "StringNotEquals": {
                    "aws:SourceVpc": "vpc-08abc123",
                    "aws:PrincipalTag/VpcLimited": "false"
                }
            }
        },
        {
            "Sid": "DenyFromOutsideVpcNotUsingEndpoints",
            "Effect": "Deny",
            "Action": "*",
            "Resource": "*",
            "Condition": {
                "Bool": {
                    "aws:ViaAWSService": "false"
                },
                "Null": {
                    "aws:SourceVpc": "true"
                },
                "NotIpAddress": {
                    "aws:SourceIp": ["1.2.3.1/32", "1.2.3.2/32", "1.2.3.3/32"]
                },
                "StringNotEquals": {
                    "aws:PrincipalTag/VpcLimited": "false"
                }
            }
        }
    ]
}
```

For roles and users within the prod OU, this would require AWS API calls to be 
made either through a VPC endpoint (for services where those have been 
configured) or via the elastic IP addresses associated with the NAT gateway. In 
a sufficiently complex account,  there are likely going to need to be exceptions - 
and for those IAM roles you  can add a `VpcLimited = false` tag. 

## Wrap up

So there you have it: VPC sharing can improve security posture and reduce costs
at the same time. Or at least it feels that way to me. I feel like I could be 
missing something as I'm yet to see anyone talk about using this pattern. 

I'd be keen to hear from folks who think this isn't feasible, please reach out 
to  me on [Twitter][my-twitter]. **EDIT**: My gratitude to [Sean McLaughlin][sean] 
who did exactly that. I've amended the SCP to account for non-endpoint use and 
reworded to (hopefully) clarify.

## The boring details

NAT Gateways are $0.045 per hour. They are also AZ-specific. So that is 3 
availability zones * 730 hours in a month * $0.045/hr = **$99 per
month** per VPC.

Lets say you also use VPC interface endpoints for various AWS services. Those 
are $0.01 per hour per availability zone = **$22 per month per service** per VPC. 
That adds up quickly if your app uses a handful of services. SQS, SNS, KMS, 
STS, X-Ray, ECR, ECS are a reasonable example for a modern containerised app.

Maybe the above is all too much, so you instead decide to centralise things
using [AWS Transit Gateway][tgw]. That is $0.05 per hour = **$37
per month** per VPC. And a few hundred thousand more per year for the network 
engineers that can actually understand it.


[launch-blog]: https://aws.amazon.com/blogs/networking-and-content-delivery/vpc-sharing-a-new-approach-to-multiple-accounts-and-vpc-management/
[tweets]: https://twitter.com/hhopk/status/1477003096572186630
[boundary]: https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html
[my-twitter]: https://twitter.com/__steele
[sean]: https://twitter.com/AliceRoryDad
[tgw]: https://aws.amazon.com/transit-gateway/
