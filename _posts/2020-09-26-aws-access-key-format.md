---
layout: post
title:  AWS Access Key ID formats
date:   2020-09-26 10:40:52 +1000
categories: blog
---

## Experimentation

I was thinking about AWS access key IDs yesterday. Specifically, the one that's
often in the `AWS_ACCESS_KEY_ID` environment variable, or `aws_access_key_id`
in `~/.aws/credentials`. I was trawling through CloudTrail and the repetitive
nature of them caught my eye.

Here's an example key we'll refer to for this example: `ASIAY34FZKBOKMUTVV7A`.
Firstly, the format of the first four characters is actually [documented][docs] and
reasonably well-known: `AKIA` is for long-lived access keys (i.e. those that are
assigned to IAM users) and `ASIA` is for temporary access keys (i.e. those returned
by `sts:AssumeRole` and so on.)

![screenshot](/assets/2020-09-26-iam-unique-id-prefixes.png)

Beyond that, I'm not aware of any documentation on the format. A couple of years 
ago, Scott Piper of Summit Route did some research and wrote down his [findings][scott].
(I didn't find this blog post until after I did yesterday's research, would have 
saved me a lot of time!) There's also the error message returned by `sts:GetAccessKeyInfo`:

```
$ aws sts get-access-key-info --access-key-id A

Parameter validation failed:
Invalid length for parameter AccessKeyId, value: 1, valid range: 16-inf
```

So we know that it needs to be at least 16 characters - but I've personally only
ever seen 20-character long key IDs.

I noticed that the characters were always alphanumeric (A-Z0-9), but not the 
entire 36 character set. `0`, `1`, `8` and `9` were absent. That leaves us with
32 characters - a nice even five bits per character. So the total set of valid
characters is `ABCDEFGHIJKLMNOPQRSTUVWXYZ234567`.

I noticed that `keyid[4:12]` (the eight characters after the AKIA/ASIA prefix)
were almost always the same value for a given AWS account. On a whim, I decided
to pass an almost-valid-but-last-character-changed to `sts:GetAccessKeyInfo` and
it still returned the same account number! This means that there isn't some kind
of checksum. Interesting. I incrementally worked out I could completely change
`keyid[13:20]` (the last seven characters) and the returned account ID would be
unaffected.

`keyid[12]` was interesting. It would add or subtract 1 from the numeric account
ID depending on if it was before/after the letter Q in the alphabet.

Lets recap so far: `keyid[4:13]` are somehow related to the account ID (with the
last one being kinda weird) and `keyid[13:20]` appear to be completely random.
I wanted to see if I could reverse-engineer the algorithm that `sts:GetAccessKeyInfo`
is using.

I ran the following to see what changing `keyid[11]` would do:

```
$ aws sts get-access-key-info --access-key-id ASIAY34FZKBOKMUTVV7A --query Account
"609629065308"

                                                         | `O` changed to `N`
$ aws sts get-access-key-info --access-key-id ASIAY34FZKBNKMUTVV7A --query Account
"609629065306"
```

So it was reduced by 2. Then I tried decrementing `keyid[10]` (`ASIAY34FZKAOKMUTVV7A`) 
and got `609629065244` - a reduction of 64. Looks like this is big-endian. I
found that a `keyid[4:12]` of `QAAAAAAA` would result in an account ID of 
`000000000000` and `6RVFFB77` in `999999999998`. 

## The resulting code

I used this knowledge to write following Go code to reproduce `sts:GetAccessKeyInfo`:

```go
package main

import (
	"fmt"
	"strconv"
	"strings"
	"github.com/kenshaw/baseconv"
)

// technically this code works equally well for principal IDs (e.g. AROA or AIDA prefixes) but
// i don't want to make the code sample any more complex
var ErrMissingPrefix = errors.New("only keys with AKIA or ASIA prefixes are supported")
var ErrUnsupportedKey = errors.New("old-format keys (created before ~early 2019) are unsupported")

func getAccessKeyInfo(accessKeyId string) (string, error) {
	if strings.HasPrefix(accessKeyId, "AKIA") || strings.HasPrefix(accessKeyId, "ASIA") {
		if accessKeyId[5] < 'Q' {
			return "", ErrUnsupportedKey
		}
	} else {
		return "", ErrMissingPrefix
	}

	base10 := "0123456789"
	base32AwsFlavour := "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

	offsetStr, _ := baseconv.Convert("QAAAAAAA", base32AwsFlavour, base10)
	offset, _ := strconv.Atoi(offsetStr)

	offsetAccountIdStr, _ := baseconv.Convert(accessKeyId[4:12], base32AwsFlavour, base10)
	offsetAccountId, _ := strconv.Atoi(offsetAccountIdStr)

	accountId := 2 * (offsetAccountId - offset)

	if strings.Index(base32AwsFlavour, accessKeyId[12:13]) >= strings.Index(base32AwsFlavour, "Q") {
		accountId++
	}

	return fmt.Sprintf("%012d", accountId), nil
}

func main() {	
	fmt.Println(getAccessKeyInfo("ASIAY34FZKBOKMUTVV7A"))
}
```

[Playground][play] link to try it yourself.

## Conclusion, or so I thought

I was ready to publish this blog post yesterday, but then I hit an issue. My 
access key ID for my personal IAM user hasn't been rotated since March 2016 (I
know, I know!) It begins `AKIAJ...` - what? Last I checked, J came before Q in
the alphabet and so my code returned a negative account ID. But my account ID
isn't negative. Well shit.

These types of keys are different. I looked at the distribution of `keyid[4]` 
in my CloudTrail logs. Most are in the range `Q-Z2-7`, but there are some that 
are `I` or `J`. The newer keys (range `Q-Z2-7`) can have their last bytes changed
and `sts:GetAccessKeyInfo` will still return correct results. The older keys 
(`I` and `J`) will return `ValidationError` if the last bytes are changed. They
also return the same error if the key is deleted (unlike new keys). This leads 
me to believe that the older keys have no internal structure and the account ID 
has to be looked up from a datastore. 

I asked for help on [Twitter][tweet] and got some great responses. Especially 
helpful was @NYSharpie's [tweet][nysharpie] where he noticed keys created after 
early 2019 are when it switched to >= Q. Looking in my own account seems to
corroborate that: a key from December 2018 has a `Y` and a key from May 2019 
has a `J`.

I've also [learned][old-key] that keys created before ~2010 don't even have the 
`AKIA` prefix! E.g. the key ID `1YRA5YCR63BKA0BX35G2` was created in 2008 and
the STS API will return the correct account ID for it. 

## Questions

* Anyone have any theories on what changed, and why? 

* Do you think there's a pattern to the old-style key IDs, or they're completely random?

* `sts:GetSessionToken` for my `AKIAJ` key returns `ASIAY` but I still see `ASIAJ`
  and `ASIAI` for some roles - what's going on there?

Please join the conversation if you have any wild theories, I'm keen to explore
this pointless space. Here's the [tweet][tweet] again if you want to respond.

## Updates

25/10/2023: Tal Be'ery published a [blog post][tal-blog] wherein he used
bit-shifting and masking to decode account IDs from access key IDs in Python. 
This would be more efficient than my code sample which has a condition (checking
if a character is greater than or equal to `Q`)

07/01/2024: Clarified behaviour of old `AKIA` keys and even older `AKIA`-less 
keys. Also updated code sample to explicitly fail for older keys (rather than
returning negative account IDs)

07/01/2024: [TruffleHog][trufflehog] now prints out account IDs based on Tal's 
bit-shifting code. This knowledge is becoming useful!


[docs]: https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html#identifiers-unique-ids
[scott]: https://summitroute.com/blog/2018/06/20/aws_security_credential_formats/
[play]: https://play.golang.org/p/-VgXwYUfRUC
[tweet]: https://twitter.com/__steele/status/1309419535569616901
[nysharpie]: https://twitter.com/NYSharpie/status/1309448974416457728
[old-key]: https://twitter.com/__steele/status/1742753372816728178
[tal-blog]: https://medium.com/@TalBeerySec/a-short-note-on-aws-key-id-f88cc4317489
[trufflehog]: https://trufflesecurity.com/blog/research-uncovers-aws-account-numbers-hidden-in-access-keys/
