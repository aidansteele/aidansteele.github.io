---
layout: post
title: "Micro-transactions and the first AI-native fax service"
date:
  created: 2026-04-19T00:36:42
categories:
  - SaaS
---

I've been interested in micro-transactions for about as long as I can remember.
I've wanted to sell something for a tiny amount of money ever since I learned
about PayPal's micro-transaction support via NearlyFreeSpeech, the hosting provider.
I've finally done it, by combining some of the oldest and newest tech I can think of:
faxes and AI.

<!-- more -->

Specifically, my [unofax.com project now supports x402][unofax-x402], the fledgling
micro-transaction-friendly [payment standard][x402]. The page on Unofax has 
comprehensive API documentation. Do humans read docs any more? Did they ever? 
I've written the documentation primarily to be consumed by AI agents that have 
been tasked with sending a fax, but maybe some humans will find it useful too - or
at least appreciate the cute animations.

x402 is built on cryptocurrency. With the rise of AI agents, I finally see a 
compelling use case for crypto. Not many people are comfortable handing their 
credit card details to their agent. But creating a wallet and giving the agent 
a few dollars to spend? I'd do that. 

It's hard to imagine that AI agents will want to send a lot of faxes, but I found
it equally hard to imagine I'd have a lot of human users either, and I've already 
had dozens of customers since launching the service. I've learned from that
experience that the Internet is a big place and I should just build things. So 
if there *are* ever any AI agents that want to send a fax, they'll choose the 
only AI-native fax service on the Internet. 

!!! note "AI-native"
    What makes a service AI-native? In my opinion it means it's pay-per-use (e.g.
    a fax costs USDC$0.20 per page), it doesn't require an account, and an AI
    agent can figure out how to invoke it by itself (e.g. using publicly-accessible
    docs to construct a `curl` command).


[unofax-x402]: https://unofax.com/x402
[x402]: https://www.x402.org/
