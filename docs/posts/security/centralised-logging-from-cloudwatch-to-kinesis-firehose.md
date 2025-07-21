---
layout: post
title: "Centralised logging: from CloudWatch to Kinesis Firehose"
date:
  created: 2022-12-16T22:56:52
categories:
  - AWS
---

<!-- more -->

AWS CloudWatch Logs supports automatic forwarding of logs to AWS Kinesis Data Streams
and AWS Kinesis Data Firehose. These destinations are can even be in a different
AWS account and region. This is very handy for aggregating logs from thousands
of log groups and forwarding them to a single place, like Axiom, Datadog, Splunk,
etc.

The only problem is that the docs are (to me, anyway) very confusing. They're also
very long. Look at this!

![docs sidebar](/assets/2022-12-17-docs-sidebar.png)

So this post is an attempt to explain it in my own words for a) me in the future 
when I forget all this and b) others who might stumble across it. I'm going to
focus on Kinesis Data Firehose _delivery streams_ as that is more interesting
to me, but the same applies to Kinesis Data Streams.

## Centralised logging

Here is a diagram of the relevant parts. I've made it multiple region and
multiple account to demonstrate the _most_ complex configuration. It also
works in single region configurations too.

![architecture](/assets/2022-12-17-architecture.png)

First, we'll start with the straightforward part: a template that deploys the
delivery stream, a role for the delivery stream and a backup bucket. This only
needs to be deployed to a single region in the logs destination account.

```yaml
Parameters:
  DeliveryStreamName:
    Type: String
    Default: centralised-logs
  APIKey:
    Type: String
    NoEcho: true

Resources:
  Firehose:
    Type: AWS::KinesisFirehose::DeliveryStream
    Properties:
      DeliveryStreamName: !Ref DeliveryStreamName
      DeliveryStreamType: DirectPut
      HttpEndpointDestinationConfiguration:
        RoleARN: !GetAtt FirehoseRole.Arn
        BufferingHints:
          IntervalInSeconds: 60
          SizeInMBs: 4
        EndpointConfiguration:
          Name: example
          Url: https://example.com
          AccessKey: !Ref APIKey
        RequestConfiguration:
          ContentEncoding: GZIP
        RetryOptions:
          DurationInSeconds: 60
        S3BackupMode: AllData
        S3Configuration:
          BucketARN: !Sub arn:aws:s3:::${Bucket}
          RoleARN: !GetAtt FirehoseRole.Arn
          Prefix: logs/!{timestamp:yyyy/MM/dd}/
          ErrorOutputPrefix: errors/!{firehose:error-output-type}/!{timestamp:yyyy/MM/dd}/
          CompressionFormat: GZIP
          BufferingHints:
            IntervalInSeconds: 60
            SizeInMBs: 128

  FirehoseRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: firehose.amazonaws.com
            Action: sts:AssumeRole
            Condition:
              StringEquals:
                sts:ExternalId: !Ref AWS::AccountId
      Policies:
        - PolicyName: Firehose
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action:
                  - s3:AbortMultipartUpload
                  - s3:GetBucketLocation
                  - s3:GetObject
                  - s3:ListBucket
                  - s3:ListBucketMultipartUploads
                  - s3:PutObject
                Resource:
                  - !Sub arn:aws:s3:::${Bucket}
                  - !Sub arn:aws:s3:::${Bucket}/*

  Bucket:
    DeletionPolicy: Retain
    Type: AWS::S3::Bucket

Outputs:
  FirehoseArn:
    Value: !GetAtt Firehose.Arn        
```

Delivery streams do not have resource-based policies, so by themselves they
have no way of permitting cross-account publishing. To resolve this, CloudWatch
introduces the concept of "logical destinations". These are abstractions that 
wrap a delivery stream (or Kinesis data stream) and add a) a role that the
destination itself assumes when publishing to the delivery stream and b) a
resource-based _destination policy_ that specifies who is permitted to forward
logs to this destination. 

CWL log groups can only forward logs to a CWL destination in the same region,
but a CWL destination can publish those logs to a delivery stream in a different
region. Therefore, my preferred pattern is to deploy this CloudFormation template
to the "logs destination" account in every region my org uses.

```yaml
# this line lets us use `Fn::ToJsonString` below
Transform: AWS::LanguageExtensions

Parameters:
  FirehoseArn:
    Type: String
    Default: arn:aws:firehose:us-east-1:0123456789012:deliverystream/centralised-logs
  OrgId:
    Type: String
    Default: o-abc123

Resources:
  Destination:
    Type: AWS::Logs::Destination
    Properties:
      DestinationName: CentralisedLogs
      RoleArn: !GetAtt DestinationRole.Arn
      TargetArn: !Ref FirehoseArn
      DestinationPolicy:
        Fn::ToJsonString:
          Version: '2012-10-17'
          Statement:
            - Sid: AllowMyOrg
              Effect: Allow
              Principal: "*"
              Action: logs:PutSubscriptionFilter
              Resource: !Sub arn:aws:logs:${AWS::Region}:${AWS::AccountId}:destination:CentralisedLogs
              Condition:
                StringEquals:
                  aws:PrincipalOrgID: !Ref OrgId

  DestinationRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: logs.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: Firehose
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Resource: !Ref FirehoseArn
                Action: firehose:PutRecord*
                # the AWS docs say to grant "firehose:*" -- how weird is that?

Outputs:
  DestinationArn:
    Value: !GetAtt Destination.Arn
```

With that deployed, our logs destination account is completely setup. We can move 
onto the source accounts. In those accounts we deploy this template:

```yaml
Parameters:
  LogPusherRoleName:
    Type: String
    Default: CentralisedLogsPusher

Resources:
  LogPusherRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Ref LogPusherRoleName
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Action: sts:AssumeRole
            Principal:
              Service: logs.amazonaws.com
      Policies:
        - PolicyName: PutLogEvents
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action: logs:PutLogEvents
                Resource: "*"
                # why does it need this permission? not sure. it's what the docs 
                # say and i haven't yet tested if it works without it. 
                # https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CreateSubscriptionFilter-IAMrole.html

Outputs:
  LogPusherRoleArn:
    Value: !GetAtt LogPusherRole.Arn                
```

Now you can finally create a subscription filter that forwards logs for a given
log group to that centralised delivery stream (via a CWL destination). Here's how
to do that:

```
aws logs put-subscription-filter \
  --log-group-name /aws/lambda/example-log-group \
  --filter-name CentralisedLogging \
  --filter-pattern '' \
  --destination-arn arn:aws:logs:ap-southeast-2:0123456789012:destination:CentralisedLogs \
  --role-arn arn:aws:iam::987654321012:role/CentralisedLogsPusher
```

Note that the principal calling `logs:PutSubscriptionFilter` will need permission
to call that action on the given log group *and* `iam:PassRole` on the log pusher
role ARN.
