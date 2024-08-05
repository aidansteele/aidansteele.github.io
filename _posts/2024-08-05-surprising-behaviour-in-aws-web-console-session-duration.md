---
layout: post
title: Surprising behaviour in AWS web console session duration
date: 2024-08-05 16:26:00 +1100
categories: blog
---

Credentials for AWS IAM role sessions are short-lived. By default, they last for
one hour. When calling `AssumeRole` you can request a different duration by 
passing a value between `900` (15 minutes) and `43200` (12 hours) in the 
`DurationSeconds` parameter. Note that this API call will fail if you request
a session duration longer than is configured on the role itself (in the "max
sesson duration" property). These credentials can be used by the AWS CLI and
AWS SDKs.

You can also use these credentials to log into the AWS web console. You do this
by calling the `GetSigninToken` and `Login` endpoints of the AWS federation API.
AWS provides [this documentation][fed-docs] on how to do that. The first of these
endpoints (`GetSigninToken`) allows you to pass an optional `SessionDuration`
parameter. This acts as you might expect: it defines how long the web console
session will remain valid. What surprised me: **you can start a 12 hour web
console session for a role that has a max session duration of 1 hour**. The web
console session will outlive the credentials that were used to create it. The
closest I could find to documentation of this behaviour is this line:

> The ability to create a console session that is longer than one hour is 
> intrinsic to the `getSigninToken` operation of the federation endpoint.

That doesn't feel explicit enough to me. It would be nice if the docs included
a parenthetical like _(even if the role's max session duration is only one hour)_

Other things that surprised me when I was digging into this:

CloudTrail will [log][cloudtrail] a call to this endpoint (the event name is 
`GetSigninToken`) but it doesn't log the requested `SessionDuration`. That feels 
like useful info to log: I'd like to know how often people in my organisation 
are using this.

Once you have a 12 hour console session, you can extract credentials that are
usable in your terminal. Simply open CloudShell and run this command: 

    aws configure export-credentials --format env

This will print a string that can be pasted directly into your local terminal.
The credentials are short-lived (about 10-15 minutes), but you can keep repeating
this for the full 12 hours. I learned this command from [this article][htc] on
hackingthe.cloud. 

This probably doesn't count as a security issue per se (because no one has access
to things they shouldn't have access to), but it might be concerning if your
environment relies on an assumption that role sessions are extremely short-lived.

[fed-docs]: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_enable-console-custom-url.html
[cloudtrail]: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-aws-console-sign-in-events.html#cloudtrail-event-reference-aws-console-sign-in-events-federated-user
[htc]: https://hackingthe.cloud/aws/post_exploitation/get_iam_creds_from_console_session/
