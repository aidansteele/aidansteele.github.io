---
layout: post
title: Two approaches to cross-account EventBridge
date: 2021-10-29 11:37:52 +1100
categories: blog
---

Since [November 2020][aws-blog], EventBridge has supported two methods of creating
cross-account event subscriptions. Both require a level of indirection in the 
form of an "intermediary" bus in the subscriber's account. Here are examples of
how they work. We will refer to the account whose bus has interesting events as 
account **B**. We will refer to the subscriber account as account **S**.

# The templates

## Scenario 1: Rule created by account B (bus owner)

This is the method that existed prior to the features released in November 2020.
Account **B** has the following resources:

```yaml
Resources:
  Bus:
    Type: AWS::Events::EventBus
    Properties:
      Name: publisher-bus

  ForwardToSubscriberBus:
    Type: AWS::Events::Rule
    Properties:
      EventBusName: !Ref Bus
      EventPattern:
        detail-type: [some-detail-type]
      Targets:
        - Id: subscriber-bus
          Arn: !Sub arn:aws:events:${AWS::Region}:${Account-S-Id}:event-bus/subscriber-bus
          RoleArn: !GetAtt ForwarderRole.Arn      

  ForwarderRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Action: sts:AssumeRole
            Principal:
              Service: events.amazonaws.com
      Policies:
        - PolicyName: ForwardEventsToSubscriberBus
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action: events:PutEvents
                Resource: !Sub arn:aws:events:${AWS::Region}:${Account-S-Id}:event-bus/subscriber-bus
```

And account **S**: has these resources: 

```yaml
Resources:
  Bus:
    Type: AWS::Events::EventBus
    Properties:
      Name: subscriber-bus

  EnqueueRule:
    Type: AWS::Events::Rule
    Properties:
      EventBusName: !Ref Bus
      EventPattern:
        detail-type: [some-detail-type]
      Targets:
        - Id: my-queue
          Arn: !GetAtt Queue.Arn    

  Queue:
    Type: AWS::SQS::Queue

  QueuePolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues: [!Ref Queue]
      PolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Action: sqs:SendMessage
            Resource: !GetAtt Queue.Arn
            Principal:
              Service: events.amazonaws.com
            Condition:
              ArnLike:
                aws:SourceArn: !GetAtt EnqueueRule.Arn    
```

## Scenario 2: Rule created by account S (target owner)

This is the new method that exists as of November 2020.
Account **B** has the following resources:

```yaml
Resources:
  Bus:
    Type: AWS::Events::EventBus
    Properties:
      Name: publisher-bus

  BusPolicy:
    Type: AWS::Events::EventBusPolicy
    Properties:
      EventBusName: !Ref Bus
      StatementId: AllowAnyAccountInOrgToCreateRules
      Statement:
        Effect: Allow
        Action: 
          - events:PutRule
          - events:DeleteRule
          - events:DescribeRule
          - events:DisableRule
          - events:EnableRule
          - events:PutTargets
          - events:RemoveTargets
        Resource: !Sub arn:aws:events:${AWS::Region}:${AWS::AccountId}:rule/${Bus}/*
        Principal: "*" # this is ok because of the aws:PrincipalOrgID condition below
        Condition:
          StringEquals:
            aws:PrincipalOrgID: o-yourorgid
          StringEqualsIfExists:
            events:creatorAccount: "${aws:PrincipalAccount}"
```

And account **S**: has these resources: 

```yaml
Resources:
  # only these first two new resources are different to the previous scenario
  RemoteRule:
    Type: AWS::Events::Rule
    Properties:
      EventBusName: !Sub arn:aws:events:${AWS::Region}:${Account-B-Id}:event-bus/publisher-bus
      EventPattern:
        detail-type: [some-detail-type]
      Targets:
        - Id: local-bus
          Arn: !GetAtt Bus.Arn
          RoleArn: !GetAtt CrossAccountEventBridgeRole.Arn

  CrossAccountEventBridgeRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Action: sts:AssumeRole
            Principal:
              Service: events.amazonaws.com
      Policies:
        - PolicyName: PutEventsOnLocalBus
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action: events:PutEvents
                Resource: !GetAtt Bus.Arn

  # everything below this line is the same as in the previous scenario
  Bus:
    Type: AWS::Events::EventBus
    Properties:
      Name: subscriber-bus

  EnqueueRule:
    Type: AWS::Events::Rule
    Properties:
      EventBusName: !Ref Bus
      EventPattern:
        detail-type: [some-detail-type]
      Targets:
        - Id: my-queue
          Arn: !GetAtt Queue.Arn    

  Queue:
    Type: AWS::SQS::Queue

  QueuePolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues: [!Ref Queue]
      PolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Action: sqs:SendMessage
            Resource: !GetAtt Queue.Arn
            Principal:
              Service: events.amazonaws.com
            Condition:
              ArnLike:
                aws:SourceArn: !GetAtt EnqueueRule.Arn    
```

# Discussion

Both approaches work equally well. Which one is best for you depends on how your
organisation works. 

In the first scenario, where the bus owner creates the rules, the event publisher 
needs to know the ARNs of every subscriber's event bus - but the subscriber doesn't
need to know where the events are coming from.

In the second scenario, the bus owner doesn't need to know anything about its
subscribers - it just sends events to its local bus. But the subscribers need
to know the ARN of the bus that events are being published to.

[aws-blog]: https://aws.amazon.com/blogs/compute/simplifying-cross-account-access-with-amazon-eventbridge-resource-policies/
