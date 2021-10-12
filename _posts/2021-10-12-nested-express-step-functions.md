---
layout: post
title: Nested Express Step Functions
date: 2021-10-12 14:58:52 +1100
categories: blog
---

## History

AWS Step Functions are cool. Express Step Functions have always felt like they
had the _potential_ to be cool, but were missing some key features when they
launched. I think they're worth revisiting in light of recent releases. A timeline:

* December 2019: [Express workflows launched][launch]. 

* August 2020: [`ResultSelector` and instrinic functions launched][resultselector].

* November 2020: [_Synchronous_ express workflows launched][synchronous].

* September 2021: [Arbitrary AWS SDK invocations launched][aws-sdk].

These are the key launches that make it possible to have an express workflow
invoke another express workflow.

## What about the existing feature?

In May 2020, SFN released `arn:aws:states:::states:startExecution.sync:2`. This
was a welcome improvement over the original (launched in August 2019) as the JSON
output is parsed. But it only works when invoked by a standard workflow, because
`.sync` isn't support for express workflows. And even from a standard workflow,
it can't synchronously invoke an express step function because that is a different
API: `StartSyncExecution` vs `StartExecution`.

## Just show me

```yaml
Resources:
  Parent:
    Type: AWS::StepFunctions::StateMachine
    Properties:
      StateMachineType: EXPRESS
      RoleArn: !GetAtt ParentRole.Arn
      Definition:
        StartAt: Example sync step
        States:
          Example sync step:
            Type: Task
            End: true
            Parameters:
              StateMachineArn: !Ref Child
              Input.$: $
            Resource: arn:aws:states:::aws-sdk:sfn:startSyncExecution
            ResultPath: $.ChildOutput
            OutputPath: $.ChildOutput
            ResultSelector:
              Output.$: States.StringToJson($.Output)

  Child:
    Type: AWS::StepFunctions::StateMachine
    Properties:
      StateMachineType: EXPRESS
      RoleArn: !GetAtt ChildRole.Arn
      Definition:
        StartAt: Hello
        States:
          Hello:
            Type: Pass
            End: true
            Result:
              Hello: World

  ParentRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Action: sts:AssumeRole
            Principal:
              Service: states.amazonaws.com
      Policies:
        - PolicyName: AllowStartChild
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action: states:StartSyncExecution
                Resource: !Ref Child

  ChildRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Action: sts:AssumeRole
            Principal:
              Service: states.amazonaws.com
      Policies: []
```

It's not a very useful couple of step functions, but it gets the point across.
The parent state machine invokes the child state machine and then is able to
process the child's output as normal.

[launch]: https://aws.amazon.com/blogs/compute/new-express-workflows-for-aws-step-functions/
[resultselector]: https://aws.amazon.com/blogs/aws/aws-step-functions-adds-updates-to-choice-state-global-access-to-context-object-dynamic-timeouts-result-selection-and-intrinsic-functions-to-amazon-states-languages/
[synchronous]: https://aws.amazon.com/blogs/compute/new-synchronous-express-workflows-for-aws-step-functions/
[aws-sdk]: https://aws.amazon.com/blogs/aws/now-aws-step-functions-supports-200-aws-services-to-enable-easier-workflow-automation/

