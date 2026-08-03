# Etsy shop playbook template

Copy to `docs/ops/approvals/shops/<shop-id>.md` for each live shop.

```yaml
shop_id: example-folk-ink
etsy_shop_name: ""
status: draft   # draft | live | paused
niche: ""
brand_voice: default  # or pointer to brand_voice.md section
sku_prefix: BD-
fulfillment_modes: [digital_download, plot_then_ship]
shipping_profile: ""
refund_policy_summary: ""
consent_required_for_portfolio: true
cross_shop_unique_inventory: true
notes: ""
```

## Listing rules

- Titles/tags match niche; no trademark stuffing  
- Photos are owned or consented  
- Digital deliverables: BotDraw export pack or SVG as sold  
- Physical: only promise ship dates the plot queue can hit  

## Message macros

- Order received → production ETA  
- Custom request → route to booking hold flow if it’s a session  
- Refund within policy → execute; outside → escalate P1  
