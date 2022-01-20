---
layout: post
title: IPv6 and TOTP
date: 2022-01-07 09:44:52 +1100
categories: blog
---

What's the silliest use for 281 trillion IP addresses that you can think of?
That's the question I asked myself when AWS [launched support][blog] for assigning 
IPv6 prefixes to EC2 instances. 

The IPv6 prefixes are `/80`, which gives your EC2 instance 281,474,976,710,656 
IP addresses to play with. You _could_ use the feature to run 281 trillion containers 
with their own IPs (which I assume is what AWS intended for the feature), but I 
wanted to find a more fun use.

After noodling on it for a bit, I had an idea: SSH doesn't support [TOTP][totp] 
(those six digit codes that change every 30 seconds) out of the box. Neither 
does Telnet, plain old HTTP or any number of protocols. So I thought it would 
be fun to add TOTP support to **every protocol** by embedding the six digit code 
_inside the IP address_.

The result is [`ipv6-ghost-ship`][github].

[blog]: https://aws.amazon.com/about-aws/whats-new/2021/07/amazon-virtual-private-cloud-vpc-customers-can-assign-ip-prefixes-ec2-instances/
[totp]: https://en.wikipedia.org/wiki/Time-based_One-Time_Password
[github]: https://github.com/aidansteele/ipv6-ghost-ship/edit/main/README.md
