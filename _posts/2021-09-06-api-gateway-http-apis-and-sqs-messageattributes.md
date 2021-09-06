---
layout: post
title: API Gateway HTTP APIs and SQS MessageAttributes
date: 2021-09-06 18:37:52 +1100
categories: blog
---

A while ago [I asked on Twitter] if anyone knew how to knew how to set
message attributes when using AWS API Gateway (HTTP API flavour)'s integration
for `SQS-SendMessage`. I didn't get very far.

But today that changed! Here is how you do it. Hopefully this helps someone else.

```yaml
Resources:
  ApiGateway:
    Type: AWS::ApiGatewayV2::Api
    Properties:
      ProtocolType: HTTP
      Name: sqsdemo

  Stage:
    Type: AWS::ApiGatewayV2::Stage
    Properties:
      ApiId: !Ref ApiGateway
      StageName: $default
      AutoDeploy: true

  Queue:
    Type: AWS::SQS::Queue

  Role:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: 2012-10-17
        Statement:
          - Effect: Allow
            Action: sts:AssumeRole
            Principal:
              Service: apigateway.amazonaws.com
      Policies:
        - PolicyName: sqssend
          PolicyDocument:
            Version: 2012-10-17
            Statement:
              - Effect: Allow
                Action: sqs:SendMessage
                Resource: !GetAtt Queue.Arn

  Integration:
    Type: AWS::ApiGatewayV2::Integration
    Properties:
      ApiId: !Ref ApiGateway
      CredentialsArn: !GetAtt Role.Arn
      PayloadFormatVersion: "1.0"
      IntegrationType: AWS_PROXY
      IntegrationSubtype: SQS-SendMessage
      RequestParameters:
        QueueUrl: !Ref Queue
        MessageBody: $request.body
        MessageAttributes: >-
          {
            "UserAgent": {
              "DataType": "String",
              "StringValue": "${request.header.user-agent}"
            }
          }

  Route:
    Type: AWS::ApiGatewayV2::Route
    Properties:
      ApiId: !Ref ApiGateway
      RouteKey: $default
      Target: !Sub integrations/${Integration}
```

[tweet]: https://twitter.com/__steele/status/1405767835901521924

