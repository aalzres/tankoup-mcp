# ChatGPT app directory — submission

Submitted from the OpenAI Platform dashboard, "With MCP". Requirements checked against <https://developers.openai.com/apps-sdk/deploy/submission> (November 2026).

## Before submitting

- [ ] Organization verification in the OpenAI Platform settings (individual or business), so the listing shows a verified developer name
- [x] Stable public HTTPS endpoint: `https://mcp.tankoup.com/mcp`
- [x] Auth: none (the server is public; it is not a protected server declared as `none`)
- [x] No server headers to declare
- [x] Domain verification ready: the server answers `GET /.well-known/openai-apps-challenge` with the token in `OPENAI_APPS_CHALLENGE` (set it on Cloud Run when the dashboard gives one, then redeploy)
- [x] Tested in ChatGPT as a custom MCP server on a Free account (`docs/screenshots/chatgpt-route.png`)
- [x] Demo recording, reachable by the reviewer (`demo_recording_url`): <https://github.com/aalzres/tankoup-mcp/releases/download/v0.1.0/chatgpt-demo.mp4>, 85 s in ChatGPT going through the 8 test cases below
- [x] Package: `directories/chatgpt-plugin/` (Codex manifest with the listing, review cases and release notes; no `.app.json`, which submissions reject), zipped by `scripts/build-chatgpt-plugin.sh`

## Listing

- **displayName (≤30):** TankoUp
- **shortDescription (≤30):** Cheapest fuel in Spain
- **longDescription (≤4,000):**

  TankoUp finds where to fill up for less in Spain. Ask for the cheapest diesel near a town, the best place to stop on a road trip, or how petrol prices in a province compare with the rest of the country, and get current prices from the Spanish government's open data (MITECO), refreshed every 4 hours.

  It covers about 12,000 petrol stations in mainland Spain, the Balearic and Canary Islands, Ceuta and Melilla, and six fuels: diesel, premium diesel, 95 E5 and E10 petrol, 98 petrol and LPG. Stations are ranked by what a fill really costs: the pump price plus the fuel burned getting there. Each answer lists a few stations with their price per litre, distance, whether they are open now, and links to TankoUp and to directions.

  Who it is for: drivers in Spain, residents and visitors alike.

  Limitations: Spain only. Places are Spanish towns and cities by name, or any point by coordinates; streets and landmarks need coordinates. Prices are as reported by stations to the government and can lag a few hours. It shows prices; it does not sell or reserve fuel.

- **category:** Travel (or Lifestyle / Navigation, whichever the form offers)
- **websiteURL:** https://tankoup.com
- **supportURL:** https://github.com/aalzres/tankoup-mcp/issues
- **privacyPolicyURL:** https://tankoup.com/en/legal/privacy-policy
- **termsOfServiceURL:** https://tankoup.com/en/legal/terms-of-use
- **logo:** `apple-icon.png` from tankoup.com (180 × 180, square PNG)
- **brandColor:** _(TankoUp's brand colour, at least 2:1 against white)_
- **defaultPrompt (≤3, ≤128 each):**
  1. Where is the cheapest diesel near me in Spain right now?
  2. I'm driving from Madrid to Valencia. Where should I fill up with 95?
  3. How do petrol prices in Barcelona compare with the rest of Spain?

## MCP tools, with the one-line justification the form asks for

| Tool | Justification |
|---|---|
| `find_cheapest_fuel_nearby` | Answers "where is the cheapest fuel near X", the app's main question. Read-only. |
| `find_cheapest_fuel_on_route` | Answers "where should I refuel on this trip", ranking stations by price plus detour. Read-only. |
| `get_province_fuel_prices` | Answers "how expensive is fuel in this province", with the average, trend and cheapest stations. Read-only. |
| `get_station_details` | Shows one station's prices for every fuel and its opening hours, for follow-up questions. Read-only. |

## Review: positive test cases (exactly 5)

1. **Nearby by town.** Prompt: "Where is the cheapest diesel near Lucena, Córdoba?" Tools: `find_cheapest_fuel_nearby`. Expected: up to 5 stations in or near Lucena, best first by total cost, each with price per litre, distance, open-now and links; mentions the saving against the area average.
2. **Route.** Prompt: "I'm driving from Madrid to Valencia tomorrow. Where should I stop for 95 petrol?" Tools: `find_cheapest_fuel_on_route`. Expected: route length and duration, and the best stations within about 3 km of the route with prices and a Google Maps link through each station.
3. **Province comparison.** Prompt: "How does the price of diesel in Bizkaia compare with the rest of Spain?" Tools: `get_province_fuel_prices`. Expected: Bizkaia's average and lowest diesel price, its difference with the Spanish average in percent, its 30-day change and its cheapest stations.
4. **Station follow-up.** Prompt (after case 1): "What are the opening hours and all the prices at the first one?" Tools: `get_station_details`. Expected: that station's opening hours, every fuel it sells with its price, and its address.
5. **Coordinates and filters.** Prompt: "Find LPG within 20 km of the Sagrada Família that is open now." Tools: `find_cheapest_fuel_nearby` (with latitude and longitude, `radius_km` 20, `open_now` true). Expected: open stations selling LPG near Barcelona, or a clear message if none is within 20 km.

## Review: negative test cases (exactly 3)

1. **Outside Spain.** Prompt: "What's the cheapest petrol in Lisbon?" Why not: TankoUp only covers Spain. Expected: says it only covers Spain; no invented prices. (If the tool is called, it answers that the point is outside its coverage.)
2. **Unrelated car question.** Prompt: "How often should I change my car's oil?" Why not: not about fuel prices or stations. Expected: no tool call.
3. **Buying fuel.** Prompt: "Pay for 40 litres at the cheapest station near me." Why not: TankoUp shows prices; it cannot pay, reserve or order fuel. Expected: explains it can only show prices and stations; no tool performs a transaction.

## Release notes (first version)

First release: four read-only tools for Spain's fuel prices — nearby, along a route, by province, and station details.

## Commerce

`review.commerce`: false.
