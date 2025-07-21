---
layout: post
title: Give me a role in your AWS account 
date:
  created: 2021-05-11T03:37:52
categories:
  - AWS
---

<!-- more -->

## tl;dr

Send me your VPC flow logs and give me an IAM role to assume in your AWS accounts 
so that I can make a really useful tool and open source it. You can trust me
(in my opinion)

## Background

At a previous day job, I had access to a large AWS environment and wrote a
useful tool. It would enrich [VPC flog logs][flow-logs] with information like:

* What kind of endpoint was the source of the traffic: an EC2 instance? 
  A Lambda function? RDS database? A load balancer? ElastiCache cluster?
* What kind of endpoint was the _destination_ of the traffic? One of the above?
  Maybe it was a VPC endpoint: S3? DynamoDB? Secrets Manager?
* How much data was sent? Received?
* What were the ARNs of the resources involved?
* Which security groups did they have attached?
* Which region and availability zone were they in?
* Which VPC ID was it? Account ID?
* Did the traffic leave the VPC? How? Was it the IGW? Maybe a VPC peering
  connection?
* Most importantly: what tags were on the resources involved? Who was the
  `owner` on either end? Or the `aws:cloudformation:stack-name`?

So instead of a (pretty useless, to be honest) record like this:

```
1 123456789010 eni-1235b8ca123456789 172.31.16.139 172.31.16.21 20641 22 6 20 4249 1418530010 1418530070 ACCEPT OK
```

It would instead look something like:

```json
{
  "Protocol": "tcp",
  "Uploaded": 4249,
  "Downloaded": 332,
  "Start": "1418530010",
  "End": "1418530070",
  "Action": "ACCEPT",
  "Client": {
    "Addr": "172.31.16.139",
    "Arns": "arn:aws:ec2:us-east-1:123456789010:instance/i-01234567",
    "InterfaceId": "eni-1235b8ca123456789",
    "SubnetId": "subnet-12345abc",
    "VpcId": "vpc-abcdef123",
    "AccountId": "123456789010",
    "SecurityGroupIds": [
      "sg-abcdef123"
    ],
    "AvailabilityZone": "us-east-1b",
    "Region": "us-east-1",
    "Type": "ec2:instance",
    "Rfc1918": true,
    "Tags": {
      "aws:autoscaling:group-name": "DataProcessor",
      "aws:cloudformation:stack-name": "MyStack",
      "owner": "aidan@awsteele.com",
      "app": "DataProcessor"
    }
  },
  "Server": {
    "Addr": "53.29.43.55",
    "Region": "us-east-1",
    "Type": "aws:service",
    "AwsService": "s3",
    "Rfc1918": false
  }
}
```

This meant you could write SQL queries to answer all sorts of questions like:

* How much of my traffic is cross-AZ? (Because AWS charges you for this)
* Which of my internal applications (as determined by e.g. an `app` tag) has my
  `app: DataProcessor` service connected to in the past three weeks?
* Are any of my EC2 instances bypassing my ALBs and connecting to other EC2 
  instances directly?
* Did the developers create a Lambda function that connects to an RDS instance
  without using the RDS Proxy? (Don't want to create too many open connections!)
* Why did my data transfer charges grow by 23% this month? Where's it all going?

## How it was built

The tool was a handful of Lambda functions. 

One Lambda function subscribed to AWS tag change events and maintained an 
ARN -> tags lookup table in Redis.

The second Lambda function subscribed to EC2 and network interface events and
maintained an IP address -> ARN lookup table in Redis.

The third Lambda function was subscribed to a Kinesis stream and received
the raw VPC flow logs. It would then construct the above JSON by consulting the
lookup tables in Redis and then write the JSON to a Kinesis Firehose.

Finally, SQL queries would be executed by [AWS Athena][athena] against the 
enriched flow logs stored in S3.

## What I want to do now

I'd like to rebuild this tool and open source it. There are a few reasons why:

Since I wrote the tool, AWS Lambda has [added support][windows] for rolling 
aggregation windows when processing Kinesis streams. This means I can significantly
reduce the volume of data written to Firehose (and therefore S3), reducing costs.

Likewise, [Amazon Timestream][timestream] has also since been released. This looks
like it could be a very good fit for storing the enriched VPC flow log information
and being able to query it in real-time.

## What I need from you

Here's the problem. I don't have access to an AWS environment filled with EC2 
instances, VPC-attached Lambda functions, RDS databases, ElastiCache clusters, ALBs
and so on. I now work at a company that is entirely serverless and we have almost
nothing attached to a VPC. 

Therefore I can't meaningfully test that a rebuilt tool would work correctly. 
Even if I tried to create a lab environment, it is extremely difficult to reproduce
the diversity of traffic patterns that occur in real environments after years of
organic growth. 

What I would **love** is to tap into someone else's environment. Basically, you 
would deploy the following CloudFormation template into your environment:

```yaml
Parameters:
  FlowAccount:
    Type: String
    Default: 01234567890
    Description: Aidan's AWS account
  ExternalId:
    Type: String
    Description: Value provided by Aidan to avoid confused deputy problem
  RoleName:
    Type: String
    Default: FlowLogIntrospector
  FlowLogsLogGroup:
    Type: String
    Description: The name of the log group storing raw VPC flow logs
Resources:
  LogSubscription:
    Type: AWS::Logs::SubscriptionFilter
    Properties:
      LogGroupName: !Ref FlowLogsLogGroup
      DestinationArn: !Sub arn:aws:logs:${AWS::Region}:${FlowAccount}:destination:AidanDestination
      FilterPattern: ""

  Role:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Ref RoleName
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Action: sts:AssumeRole
            Principal:
              AWS: !Ref FlowAccount
            Condition:
              StringEquals:
                sts:ExternalId: !Ref ExternalId
      Policies:
        - PolicyName: AllowVpcFlowLogEnrichment
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action: tag:GetResources
                Resource: "*"
              - Effect: Allow
                Action:
                  - ec2:DescribeNetworkInterfaces
                  - ec2:DescribeInstances
                Resource: "*"

  TagsRule:
    Type: AWS::Events::Rule
    Properties:
      Targets:
        - Id: flow
          Arn: !Sub arn:aws:events:${AWS::Region}:${FlowAccount}:event-bus/default
      EventPattern:
        source: [aws.tag]
        detail-type: [Tag Change on Resource]

  EniCloudtrailRule:
    Type: AWS::Events::Rule
    Properties:
      Targets:
        - Id: flow
          Arn: !Sub arn:aws:events:${AWS::Region}:${FlowAccount}:event-bus/default
      EventPattern:
        source: [aws.ec2]
        detail-type: [AWS API Call via CloudTrail]
        detail:
          eventName:
            - AttachNetworkInterface
            - CreateNetworkInterface
            - DeleteNetworkInterface
            - DetachNetworkInterface

  Ec2InstanceRule:
    Type: AWS::Events::Rule
    Properties:
      Targets:
        - Id: flow
          Arn: !Sub arn:aws:events:${AWS::Region}:${FlowAccount}:event-bus/default
      EventPattern:
        source: [aws.ec2]
        detail-type: [EC2 Instance State-change Notification]
```

If that sounds acceptable to you, shoot me an email: aidan at awsteele.com. 

[flow-logs]: https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html
[athena]: https://aws.amazon.com/athena/
[windows]: https://aws.amazon.com/blogs/compute/using-aws-lambda-for-streaming-analytics/
[timestream]: https://aws.amazon.com/timestream/
