---
layout: post
title: Step Function execution name format
date:
  created: 2026-04-01T09:00:00
categories:
  - AWS
---

I was looking at the execution history for a Step Functions state machine that
is triggered daily by an EventBridge Scheduler schedule. The execution names
caught my eye — they _look_ like UUIDs, they're not UUIDv7, but there's clearly 
a pattern. It got me excited in the same way that noticing [AWS access key IDs
were similarly-formatted][access-key-format] back in 2020. So of course I had
to dig in.

<!-- more -->

Look at these execution names, and their corresponding timestamps. How could you
not be intrigued?

```
4b69cbb7-4050-4cf0-a096-4a0307b92a1a  2026-03-31 12:01:30 UTC
4b69ca65-c050-4cf0-a096-4a0307b92a1a  2026-03-30 12:01:30 UTC
4b69c914-4050-4cf0-a096-4a0307b92a1a  2026-03-29 12:01:30 UTC
4b69c7c2-c050-4cf0-a096-4a0307b92a1a  2026-03-28 12:01:30 UTC
4b69c671-4050-4cf0-a096-4a0307b92a1a  2026-03-27 12:01:30 UTC
4b69c51f-c050-4cf0-a096-4a0307b92a1a  2026-03-26 12:01:30 UTC
4b69c3ce-4050-4cf0-a096-4a0307b92a1a  2026-03-25 12:01:30 UTC
4b69c27c-c050-4cf0-a096-4a0307b92a1a  2026-03-24 12:01:30 UTC
```

The last ten bytes are always the same. The second segment alternates between
`4050` and `c050`. The first segment increments by a small amount each day. 
These are clearly not random UUIDs. So what's going on?

## The structure

It turns out these are UUID-shaped deterministic identifiers with an embedded
timestamp. The 16 bytes break down like this:

```
[1 byte seed] [4 byte unix timestamp] [1 byte fixed] [10 bytes fixed]
```

Rendered as a UUID string:

```
SSTTTTTT-TTFF-4xxx-xxxx-xxxxxxxxxxxx
│ │       │ │  │
│ │       │ │  └── per-schedule constant (fingerprint)
│ │       │ └───── fixed byte
│ │       └─────── low byte of timestamp
│ └────────────── upper 3 bytes of timestamp
└──────────────── schedule-specific seed byte
```

The UUID version nibble is forced to `4` and the variant bits are set to RFC 4122,
so it _looks_ like a standard UUID v4 at first glance. But the content is entirely 
deterministic.

## What timestamp?

The 4-byte timestamp is the **scheduled fire time** in unix seconds — not the 
actual execution start time. My schedule uses `cron(0 22 * * ? *)` in the 
`Australia/Brisbane` timezone, which is 12:00:00 UTC. The actual executions start
at 12:01:30 UTC (due to the `FlexibleTimeWindow` being set to `FLEXIBLE` with a 
60-minute maximum), but the embedded timestamp is exactly 12:00:00 UTC every time.

At first I thought the timestamp was truncated to the hour. To test this, I
deployed two additional schedules targeting the same state machine: one firing
every 2 minutes and one every 3 minutes. This quickly disproved the truncation
theory — the embedded timestamps had **full second precision**:

```
Schedule A (every 3 min):  bucket deltas = exactly 180 seconds
Schedule B (every 2 min):  bucket deltas = exactly 120 seconds
```

The daily schedule only _appeared_ to be hour-truncated because the cron 
expression fires exactly on the hour. Also because I had forgotten I had set a
flexible time window - oops.

## The per-schedule fingerprint

Everything except the 4 timestamp bytes is constant for a given schedule. Different
schedules get different fingerprints:

| Schedule | Seed byte | Fingerprint |
|---|---|---|
| Daily cron | `0x4b` | `4cf0-a096-4a0307b92a1a` |
| Every 3 min | `0xbd` | `4afa-8e02-9f1a19cda44c` |
| Every 2 min | `0x79` | `4970-9d19-dcca01bbea4b` |

This means two different schedules firing at the exact same second will never
produce the same execution name. I confirmed this: the 2-min and 3-min schedules
both had their first invocation at the same second (`09:41:57 UTC`) and produced
different, non-colliding names.

## Why does Amazon do this?

**Idempotent delivery**. EventBridge Scheduler has at-least-once delivery
semantics. If it accidentally delivers the same scheduled invocation twice 
(retries, network hiccups, cosmic rays, etc.), the execution name will be 
identical both times. Step Functions requires execution names to be unique, so 
the second `StartExecution` call is silently rejected as a duplicate.

This is actually a really elegant design. Amazon needed to solve two problems 
at once: generate names that are unique across invocations but identical across
retries of the _same_ invocation. Embedding the scheduled fire time achieves both.

## Monotonically increasing

There's a nice bonus: for a given schedule, the execution names are 
**monotonically increasing in lexicographic order**. The seed byte and fingerprint 
are constant, so the only varying part is the 4-byte big-endian timestamp split 
across the first two UUID segments. Lexicographic comparison hits the most 
significant timestamp bytes first (in segment 1), then the least significant byte 
(in segment 2), preserving the natural time ordering.

This makes them excellent DynamoDB range keys. If you're tracking schedule
executions in a DynamoDB table with the schedule ARN as the partition key and
the execution name as the range key, you get chronological ordering for free
with no additional sort keys or GSIs. You can query for the latest N executions
with `ScanIndexForward: false`, do time-range queries, and paginate — all because
the execution names happen to sort correctly. 

I'm definitely going to do this. I used to have an intermediate Lambda whose sole 
job was to invoke the state machine with a UUIDv7 execution name (so it could 
be used like this), and now I can get rid of it. Note that this only works as
long as you only have a single schedule invoking your state machine, and you
don't make any manual invocations (at least not without following the pattern
manually).

## Decoding

Here's a Go function to extract the scheduled fire time from an execution name:

```go
func decodeScheduledTime(executionName string) (time.Time, error) {
	parts := strings.Split(executionName, "-")
	bucketHex := parts[0][2:] + parts[1][:2]
	bucket, err := strconv.ParseInt(bucketHex, 16, 64)
	if err != nil {
		return time.Time{}, err
	}
	return time.Unix(bucket, 0), nil
}
```

## Should you rely on this?

This is entirely undocumented behaviour. I reverse-engineered it from a handful
of executions and it could change tomorrow. AWS has made no promises here and 
presumably has no idea I'm writing this blog post.

On the other hand, [Hyrum's Law][hyrums] tells us that _"with a sufficient 
number of users of an API, all observable behaviors of the system will be 
depended on by somebody."_ I'm now that somebody. And if you've read this far,
you might be too. So really, Amazon can't change it now — that would be a 
backwards-incompatible change, and we all know how Amazon feels about those. 
I'm sure this argument would hold up great in a support ticket.

[access-key-format]: /blog/2020/09/26/aws-access-key-format/
[hyrums]: https://www.hyrumslaw.com/
