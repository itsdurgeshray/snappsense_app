"""Suggested fixes from a rule-based playbook — free, instant, explainable.

Each play matches what users are actually complaining about (the issue's
concern sentences), so "refund pending" and "late delivery" get different,
specific fixes even though both are Transactional. The most-matched play
wins; a per-category default covers the rest.
"""

from __future__ import annotations

import re

from .cluster import Issue

T, B, C, P, S, U, A = "Transactional", "Bug Report", "Crash", "Performance", "Support", "UI/UX", "Pricing & Ads"

# (id, categories it applies to, pattern over the issue's concerns, fix)
_PLAYS: list[tuple[str, set[str], str, str]] = [
    # Money & orders
    ("payment-failed", {T, B}, r"\b(deducted|debited)\b|\bpayment (failed|failure|pending|stuck)|\bmoney\b.*\b(gone|lost|stuck)", "Auto-reconcile failed payments and refund within 24 h; show payment status on the order page so users aren't left guessing."),
    ("refund", {T, S}, r"\brefund", "Automate refunds as soon as a return is picked up, and show a refund tracker with the expected credit date."),
    ("trial-charge", {T, A}, r"\b(charged|billed|deducted)\b.*\b(trial|cancel\w*|without)|\bfree trial\b|\bauto.?renew", "Send a reminder 2 days before a trial or renewal charges, and make cancelling possible in two taps from settings."),
    ("delivery-delay", {T}, r"\b(late|delay\w*|not (been )?deliver\w*|didn'?t deliver|still (not|haven'?t) received|not received|deliver\w* (date|time|on time))\b|\bfast delivery\b", "Set realistic delivery dates per pincode, send proactive delay alerts with a new ETA, and auto-compensate long delays."),
    ("cancellation", {T}, r"\bcancel+ed\b|\bcancel+ation\b", "Explain why an order was cancelled, notify before seller cancellations and offer an instant alternative or credit."),
    ("returns", {T}, r"\b(return|replacement|exchange)\b", "Simplify the return flow: instant pickup slots, clear eligibility upfront and status updates at every step."),
    ("product-quality", {T}, r"\b(fake|damaged|wrong|defective|used|duplicate|broken) (product|item)|\bquality\b", "Tighten seller quality checks for the flagged categories and fast-track replacements for damaged or wrong items."),
    ("payment-method", {T, B}, r"\b(payment|card|upi|wallet)\b.*\b(not|doesn'?t|won'?t|fail|accept|declin)", "Fix the failing payment methods first (log decline codes by method/bank) and offer a fallback method in the same flow."),
    ("billing-plans", {T, A}, r"\b(annual|yearly|monthly)\b.*\b(plan|payment|subscription)", "Restore the billing options users are asking for and make plan changes self-serve."),
    ("playback-order", {T, B, U}, r"\b(queue|shuffle|repeat|play in order|in order|rewind|skip)\b", "Fix playback-control bugs (queue, order, rewind/skip) and add automated tests for the core player flows."),
    # Monetisation
    ("price-high", {A}, r"\b(price|prices|pricing)\b|\boverpriced\b|\bexpensive\b|\bcostly\b", "Audit price changes around sales; show price history, keep 'sale' prices genuinely lower, and test regional pricing."),
    ("ads-for-payers", {A}, r"\bads?\b.*\b(premium|paid|pay)\b|\b(premium|paid)\b.*\bads?\b", "Make sure paying users never see ads; audit ad placements that leak into premium surfaces."),
    ("ads-volume", {A}, r"\bads?\b|\badvert", "Cap ads per session, never interrupt core actions, and make every ad closable; test a lower-frequency variant."),
    ("free-tier", {A}, r"\b(without|need|require\w*|force\w*|have to|only)\b.*\b(premium|subscription|pay)|\bfree (version|tier|plan)\b", "Rebalance the free tier: keep the core experience usable without paying and gate only clear extras behind premium."),
    ("subscription", {A, T}, r"\bsubscription\b|\bpremium\b|\brenew", "Make plan value and pricing transparent before purchase, and let users manage or cancel subscriptions in-app."),
    # Accounts & reliability
    ("otp", {B, T}, r"\botp\b|\bverification code\b|\bsms\b", "Add fallback OTP channels (voice, WhatsApp, email), a visible resend timer, and monitor SMS delivery by carrier."),
    ("account-suspended", {B, S}, r"\b(disabled?|banned|blocked|suspended|locked|hacked|deactivated)\b", "Give suspended users a clear reason and a working appeal flow with a response-time commitment."),
    ("login", {B}, r"\b(log ?in(?:to)?|sign ?in(?:to)?|login|log me out|logged out|password|access (my|the) account)\b", "Fix the failing login paths (track success rate by method/device), keep sessions alive and add clear recovery steps."),
    ("streak", {B, C}, r"\bstreak", "Protect streaks from app/notification failures: auto-restore when the miss was on our side and make freezes visible."),
    ("notifications", {B, U}, r"\bnotification", "Fix notification delivery reliability and add per-category notification controls."),
    ("speech", {B, P}, r"\b(mic|microphone|speech|voice recognition|speaking|speak)\b", "Improve speech recognition tolerance and give users a reliable 'can't speak now' option."),
    ("devices", {B, C}, r"\b(bluetooth|car|android auto|carplay|chromecast|cast|samsung|xiaomi|pixel|tablet|ipad|fold)\b", "Reproduce on the reported devices and accessories, then add them to the release test matrix."),
    ("search", {B, U, P}, r"\bsearch", "Fix search reliability first, then improve relevance and typo tolerance; log zero-result queries to tune it."),
    ("regression", {B, C, U, P}, r"\bupdate\b", "Roll back or hot-fix the regression from the latest release; use staged rollouts with crash and error gates."),
    # Crashes & performance
    ("launch-failure", {C, B}, r"\b(not open\w*|won'?t open|doesn'?t open|not load\w*|stuck on (the )?(loading|splash))", "Fix the launch failure: check startup crashes by device/OS in crash reporting and add a safe-mode start path."),
    ("crash", {C}, r"\bcrash\w*|\bfreez\w*|\bforce clos|\bhang", "Prioritise the top crash signatures for the affected devices/OS versions and gate releases on crash-free rate."),
    ("battery", {P}, r"\bbattery|\bdrain\w*|\bheat\w*|\bvibrat", "Audit background work, wake-locks and vibrations; batch syncs and respect battery-saver mode."),
    ("storage", {P}, r"\bstorage\b|\bspace\b|\b(app )?size\b|\bheavy\b", "Reduce app size and cache growth; let users clear downloads/cache from settings."),
    ("payment-slow", {P}, r"\bpayment\b", "Profile the checkout and payment steps end to end; add timeouts with clear retry and status messaging."),
    ("slow", {P}, r"\bslow|\blag\w*|\bload\w*|takes forever", "Profile the slow screens on low-end devices; cache responses, lazy-load images and cut startup work."),
    # Support & UX
    ("support-access", {S, B, T}, r"\b(customer (care|service|support|survice)|support|contact|response|reply|helpline|real person|talk to)\b", "Offer in-app chat with escalation to a human, a response-time promise and ticket status tracking."),
    ("redesign", {U}, r"\b(new|latest|recent) (update|ui|interface|design|layout)|\bold (ui|version|design|layout)|\binterface\b|\blayout\b|\bui\b", "Usability-test the redesigned flows with existing users; restore the most-missed paths or offer a short guided tour."),
    ("navigation", {U}, r"\bconfus\w*|\bhard to (find|use)|\bnavigat\w*|\bnot user.?friendly", "Simplify navigation for the confusing journeys and run quick usability tests before the next release."),
    ("unresponsive-ui", {U, B}, r"\b(tap|tapped|button|icon|bar)s?\b.*\b(not|can'?t|cannot|doesn'?t)", "Fix unresponsive controls on the reported devices/screen sizes and add UI tests for tap targets."),
]
# ---------------------------------------------------------------------------
# App-type playbooks. Eligible only for apps in that domain (from the store
# genre) and preferred over general plays when both fit.
# ---------------------------------------------------------------------------
F = "Feature Request"
_DOMAIN_PLAYS: dict[str, list[tuple[str, set[str], str, str]]] = {
    "food": [
        ("food-late", {T, P}, r"\b(late|delay\w*|cold|took (an? )?hours?|waiting)\b", "Track kitchen-prep and rider ETAs separately, warn users early when an order slips, and auto-credit late or cold deliveries."),
        ("food-missing", {T}, r"\b(missing|wrong (item|order|food)|not (included|packed)|spill\w*)\b", "Add packing checklists and photo proof at handover, with one-tap refunds for missing or wrong items."),
        ("food-rider", {T, S}, r"\b(rider|delivery (boy|guy|partner|executive)|driver)\b", "Give users rider ratings that matter, live rider tracking and a quick way to report rider behaviour with follow-up."),
        ("food-fees", {A, T}, r"\b(delivery fee|platform fee|packaging|surge|extra charges?|taxes|hidden)\b", "Show every fee before checkout, cap surge pricing and explain the breakdown in the cart."),
    ],
    "finance": [
        ("fin-kyc", {B, T, S}, r"\b(kyc|verification|verify|documents?|aadhaar|pan|selfie|id proof)\b", "Shorten KYC: say exactly which document failed and why, allow in-app resubmission and show the review ETA."),
        ("fin-transfer", {T, B}, r"\b(transfer|upi|transaction|money)\b.*\b(failed|stuck|pending|not (received|credited|reflect\w*)|deducted)\b", "Auto-reverse failed transfers, show the bank reference number and the guaranteed reversal time on the transaction."),
        ("fin-frozen", {B, S, T}, r"\b(frozen|freeze|blocked|suspended|restricted|on hold)\b", "Tell users why an account is restricted, what they need to provide, and offer a human review within a fixed SLA."),
        ("fin-fees", {A, T}, r"\b(fees?|charges?|interest|hidden|annual)\b", "Make every fee and interest charge visible before confirmation and notify users before any new charge applies."),
        ("fin-fraud", {B, S, T}, r"\b(fraud|scam|unauthori[sz]ed|hacked|stolen)\b", "Add instant card/account freeze, real-time transaction alerts and a 24×7 fraud-reporting path with case tracking."),
    ],
    "streaming": [
        ("stream-offline", {B, F, A}, r"\b(offline|download\w*)\b", "Make downloads reliable (resume on failure, clear storage use) and confirm what's available offline before travel."),
        ("stream-buffer", {B, P}, r"\b(buffer\w*|stops? playing|pauses?|cuts? out|skipping|stutter\w*)\b", "Tune adaptive bitrate and pre-buffering for weak networks; log playback stalls by network type and device."),
        ("stream-recs", {U, F, B}, r"\b(recommend\w*|algorithm|suggest\w*|same songs|repeat\w*)\b", "Let users reset or tune recommendations and add a 'don't play this' control that the algorithm actually respects."),
        ("stream-free-limits", {A}, r"\b(shuffle|skip\w*|choose|pick|on demand)\b.*\b(free|premium)\b|\b(free|premium)\b.*\b(shuffle|skip\w*|choose|pick)\b", "Loosen the most-resented free-tier limits (skips, picking songs) and test which limits actually drive upgrades."),
    ],
    "education": [
        ("edu-hearts", {A, B, U}, r"\b(hearts?|energy|lives)\b", "Rebalance hearts/energy so mistakes don't block learning; let practice refill them and keep core lessons free."),
        ("edu-answers", {B, U}, r"\b(wrong|incorrect|marked|translation|accept\w*)\b.*\b(answer|correct|translation)\b|\b(answer|translation)\b.*\b(wrong|incorrect|not accepted)\b", "Add an in-lesson 'report this answer' button and review disputed answers quickly; accept common valid variants."),
        ("edu-path", {U}, r"\b(path|levels?|units?|lessons?|curriculum|progress)\b", "Explain changes to the learning path in-app, let users choose their level, and preserve their earned progress."),
        ("edu-streak", {B, C, A}, r"\bstreak", "Protect streaks from app/notification failures: auto-restore when the miss was on our side and make freezes visible."),
    ],
    "games": [
        ("game-p2w", {A}, r"\b(pay to win|p2w|pay ?wall|gems?|coins?|spend|loot ?box)\b", "Rebalance paid advantages so free players can progress at a fair pace; audit drop rates and price points."),
        ("game-lag", {P, B}, r"\b(lag\w*|ping|server|disconnect\w*|matchmaking|desync)\b", "Add regional servers or better matchmaking by ping, and show connection quality before a match starts."),
        ("game-progress", {B, C, T}, r"\b(progress|save|account|level)\b.*\b(lost|gone|reset|deleted)\b", "Add cloud saves tied to a login, and a support flow that restores lost progress from server records."),
        ("game-ads", {A}, r"\bads?\b", "Cap forced ads per session, never show them mid-level, and make rewarded ads optional."),
        ("game-cheat", {B, S}, r"\b(cheat\w*|hack\w*|bots?|ban\w*)\b", "Strengthen anti-cheat and bot detection, and give banned players a clear reason and appeal path."),
    ],
    "social": [
        ("social-hacked", {B, S}, r"\b(hacked|compromised|someone (logged|took)|stolen)\b", "Make account recovery work without the hacked email/phone (ID check, trusted contacts) and push 2FA setup."),
        ("social-feed", {U, F}, r"\b(feed|algorithm|chronological|recent posts|see (my )?friends)\b", "Offer a chronological 'Following' feed and controls to see fewer suggested posts."),
        ("social-spam", {B, S}, r"\b(spam|fake (accounts?|profiles?)|scam\w*|bots?|impersonat\w*|pretend\w*)\b", "Speed up reports of fake accounts and impersonation, and show reporters the outcome."),
        ("social-messages", {B}, r"\b(messages?|chats?|calls?)\b.*\b(not|don'?t|doesn'?t|fail\w*|delay\w*)\b", "Fix message/call delivery reliability; log delivery failures by network and device."),
    ],
    "travel": [
        ("travel-cancel", {T, S}, r"\b(driver|captain|rider)\b.*\bcancel\w*|\bcancel\w*\b.*\b(driver|captain|ride)\b", "Penalise repeated driver cancellations, re-assign instantly, and refund any cancellation fee caused by the driver."),
        ("travel-fare", {A, T}, r"\b(fare|surge|price|charged more|extra)\b", "Lock the quoted fare, explain surge before booking and auto-refund overcharges against the route."),
        ("travel-eta", {B, P}, r"\b(eta|gps|location|map|route|pickup point)\b", "Improve pickup accuracy and ETA estimates; let users pin precise pickup points."),
    ],
    "health": [
        ("health-sync", {B}, r"\b(sync\w*|watch|tracker|steps|heart rate|google fit|health connect|apple health)\b", "Fix device and health-platform sync reliability, and show the last successful sync time."),
    ],
}
_GENRE_DOMAIN = {
    "shopping": "shopping", "food & drink": "food", "food delivery": "food", "finance": "finance", "music & audio": "streaming",
    "music": "streaming", "entertainment": "streaming", "video players & editors": "streaming", "education": "education",
    "books & reference": "education", "social": "social", "social networking": "social", "communication": "social",
    "dating": "social", "travel & local": "travel", "travel": "travel", "maps & navigation": "travel", "navigation": "travel",
    "auto & vehicles": "travel", "health & fitness": "health", "medical": "health", "games": "games",
}
_GAME_GENRES = {"action", "adventure", "arcade", "board", "card", "casino", "casual", "puzzle", "racing", "role playing", "simulation", "sports", "strategy", "trivia", "word"}


def domain_for(genre: str | None) -> str | None:
    g = (genre or "").strip().lower()
    return _GENRE_DOMAIN.get(g) or ("games" if g in _GAME_GENRES else None)


_COMPILED = [(pid, cats, re.compile(p, re.I), fix) for pid, cats, p, fix in _PLAYS]
_DOMAIN_COMPILED = {d: [(pid, cats, re.compile(p, re.I), fix) for pid, cats, p, fix in plays] for d, plays in _DOMAIN_PLAYS.items()}
_FIX_BY_ID = {pid: fix for pid, _, _, fix in _PLAYS} | {pid: fix for plays in _DOMAIN_PLAYS.values() for pid, _, _, fix in plays}
DOMAIN_BONUS = 1.25  # an app-type play beats a general one when both fit

_DEFAULTS = {
    "Crash": "Prioritise the top crash signatures from crash reporting and ship a hot-fix for the affected devices.",
    "Transactional": "Audit this order/payment flow end to end and show users clear status at every step.",
    "Bug Report": "Reproduce from the quoted reviews, add a regression test and prioritise the fix for the next release.",
    "Performance": "Profile the affected screens on low-end devices and cut the heaviest work.",
    "Support": "Add in-app escalation to a human with a response-time promise.",
    "Pricing & Ads": "Revisit pricing and ad load for this segment and test a lighter-touch variant.",
    "UI/UX": "Run a quick usability test on this journey and simplify it.",
}


def match(issue: Issue, title: str | None = None, domain: str | None = None) -> str | None:
    """Id of the play that best fits this issue's concerns (and title), or None."""
    if issue.feature and domain not in _DOMAIN_COMPILED:
        return None
    top = issue.concerns[:15]
    best, best_score = None, 0.0
    candidates = [(p, 1.0) for p in _COMPILED] + [(p, DOMAIN_BONUS) for p in _DOMAIN_COMPILED.get(domain or "", [])]
    for (pid, cats, rx, _), bonus in candidates:
        if issue.category not in cats:
            continue
        # The most central concerns count most: they define the issue.
        score = sum((2.0 if i < 5 else 1.0) for i, c in enumerate(top) if rx.search(c))
        if title and rx.search(title):
            score += 4.0
        score *= bonus
        if score > best_score:
            best, best_score = pid, score
    return best if best_score >= max(2.0, 0.2 * len(top)) else None


def suggest(issue: Issue, title: str | None = None, domain: str | None = None) -> str:
    if issue.feature:
        play = match(issue, title, domain)
        if play and play in _FIX_BY_ID:  # e.g. a streaming app asked for offline downloads
            return _FIX_BY_ID[play]
        n = issue.size
        return f"Validate demand with an in-app poll{f' ({n} users asked)' if n > 1 else ''}, then scope a small first version for the roadmap."
    play = match(issue, title, domain)
    return _FIX_BY_ID.get(play) or _DEFAULTS.get(issue.category, "Investigate the quoted reviews and prioritise a fix.")
