---
layout: post
title: unofax.com
date:
  created: 2026-03-18T19:57:00
draft: true
categories:
  - SaaS
---

I've been writing software for 25 years, and been getting paid for the last 20. 
My AWS account will be turning 18 this September, and it should be quite the 
celebration. I don't mean to toot my own horn, but I've got pretty good at writing
and deploying software in that time - to the point that you're actually spending
your time reading this blog. All this, and the release of Opus 4.5 in November 2025
hit me like a tonne of bricks. My value-add (as I knew it) would soon be over.

<!-- more -->

Is that a dramatic enough lede? I've also been blogging about software for at 
least [17 years][first-blog] and I still feel like I'm no good at it. In any case,
Opus 4.5 was huge. Let me set the scene: after my partner had been using it for 
a few months, I had finally got around to installing Claude Code in mid-November.
Opus 4.0 seemed too slow and expensive to use, and Sonnet 4.5 was the default model.
I gave it a description of a project I wanted to build: a combination of standard
AWS crud stuff and some more arcane network packet-wrangling and little-used CLI
plugin standards. It generated some surprisingly good code. Not perfect, had a
show-stopping (but fixable) bug, but definitely usable. I thought this could save
me some time. 

A week later Opus 4.5 is released, becomes the default model and
changes everything. It fixed all the bugs I identified in the code written by 
Sonnet, plus a handful of bugs I hadn't yet even noticed. It was objectively a
better programmer than I am after two decades of being hands on the tools. I've
always been in agreement with Ben Kehoe ever since I heard him [state][ben] 
(paraphrasing) that your job as a developer isn't to write code, it's to solve
problems. As much as I didn't want this to be the case, it's true. The thing that
had always most distinguished me from my peers (memorising an unreasonably large 
surface area of AWS APIs, being able to write ~complete serverless apps and infra 
without consulting docs, etc) is now a prompt away. 

Anyway, that's a very long way of saying: AI is here, it's very good at generating
whatever code you ask it to, and it's only ever going to get better. So I need to
start finding a new way to be useful. My partner and I decided that we should
take one of my many SaaS ideas from over the years and actually try to ship it.
It's a pretty big idea, and I figured we'd probably fail, so instead I suggested 
that she start with some small ideas, complete them, move onto bigger ideas, learn
and iterate in a snowball fashion. She had just quit her full-time job, so it was
perfect timing.

And that's what we did: she made some very impressive small projects, shipped
them to production and learned a lot about how to work with AI effectively. Then
we decided our next project should be a complete SaaS: users can land on a 
marketing site, use the functionality and pay for it. And that we'd build it
entirely using AI. 

So that's how we made [unofax.com][unofax]. Payments are received using Square
(my day job), hosted on AWS Lambda and AWS Step Functions (my favourite tech 
stack) and the frontend is Vite, I think? We outsource the actual fax-sending
to another company that does a great job, but requires maintaining a balance 
to send faxes. So our unique differentiator is that we don't require any sign up
and you can pay per page. Somehow, we've already made four sales, adding up to
a few dollars. That's the most surprising part to me.

Will it allow us to retire? Very unlikely. It serves more as an excuse to learn
how to ship something end-to-end, and to learn SEO, marketing, frontend dev,
customer support, etc. It also taught us what pain points we should expect when
using AI, and provides an ideal proving ground for trying new ideas to avoid 
them. Because it costs us close to nothing to run, we can also keep it running
indefinitely. It has also provided an excellent and humbling opportunity to learn
quite how inelegantly I can express my ideas, compared to where I want to be.
So I can work on that too.

What's next? I realised while writing my last blog post that it'll still take
a while before AI really understands AWS security in depth: it kinda sucks at
SCPs, RCPs and nuanced IAM. So I've probably got a day job for a while longer.
We're also starting work on our next idea, slightly bigger, more ambitious and
more relevant than a fax-sending service in 2026. Maybe that idea will earn
enough to pay for lunch every day. And then I can move onto the idea after that.

[first-blog]: https://web.archive.org/web/20120607012148/http://www.glassechidna.com.au/2009/devblogs/islands-of-serialisation-in-a-sea-of-concurrency/
[ben]: https://dev.to/aws/dev-track-spotlight-the-builders-job-is-not-to-build-a-mindset-for-better-outcomes-dev347-50b9
[unofax]: https://unofax.com