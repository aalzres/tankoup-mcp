# Claude Connectors Directory — submission

Submitted at <https://claude.ai/directory/manage> → Submit new → MCP connector, on 3 November 2026. Status: in review. Requirements checked against <https://claude.com/docs/connectors/building/submission> and the review checklist (November 2026).

## Pre-submission checklist

- [x] Remote server over HTTPS: `https://mcp.tankoup.com/mcp`
- [x] No authentication: public data, read-only tools
- [x] Every tool has a `title` and `readOnlyHint: true`; names under 64 characters
- [x] Descriptions say what each tool does; none tells the model how to behave
- [x] Errors are actionable (`"'Santa Cruz' is not a Spanish town with a fuel station. Close names: …"`), never a bare "Internal Server Error"
- [x] Responses are short: at most 10 stations, 5 by default
- [x] Calls only TankoUp's own API (first party)
- [x] Tested in MCP Inspector
- [x] Tested as a custom connector in Claude: all four tools, in English and Spanish (screenshots in `docs/screenshots/claude-*.png`)
- [x] Privacy policy covers the MCP server (section 2.5 of tankoup.com's policy, in all eight languages)

## 1. Connection

URL: `https://mcp.tankoup.com/mcp`. Users connect to one URL.

## 2. Tools

Synced from the server. All four are read-only:

| Tool | Title |
|---|---|
| `find_cheapest_fuel_nearby` | Cheapest fuel near a place |
| `find_cheapest_fuel_on_route` | Cheapest fuel along a route |
| `get_province_fuel_prices` | Fuel prices in a province |
| `get_station_details` | Petrol station details |

## 3. Listing

- **Server name:** TankoUp
- **One-liner (≤200):** Find the cheapest fuel in Spain: live prices at about 12,000 petrol stations, near any town or along your route.
- **Description (≤2,000):**

  TankoUp finds where to fill up for less in Spain. Ask for the cheapest diesel near a town, the best place to stop on a road trip, or how petrol prices in a province compare with the rest of the country, and Claude answers with current prices from the Spanish government's open data (MITECO), refreshed every 4 hours.

  It covers about 12,000 petrol stations in mainland Spain, the Balearic and Canary Islands, Ceuta and Melilla, and six fuels: diesel, premium diesel, 95 E5 and E10 petrol, 98 petrol and LPG.

  Stations are ranked by what a fill really costs: the pump price plus the fuel burned getting there, or leaving the route and rejoining it. Each answer lists a few stations with their price per litre, distance, whether they are open now, a link to open them in the TankoUp app or website, and a Google Maps directions link.

  Tools:
  - Cheapest fuel near a place: by town name or by latitude and longitude, within up to 50 km.
  - Cheapest fuel along a route: between two places, for trips up to 1,200 km.
  - Fuel prices in a province: average and lowest price, 30-day trend, comparison with Spain, cheapest brand and stations.
  - Petrol station details: every fuel's price, opening hours and address.

  No account or sign-in. The connector only reads public price data and keeps no record of what you ask.

- **Categories:** Travel & transportation; Maps & local (or the closest the portal offers)
- **Documentation URL:** https://github.com/aalzres/tankoup-mcp#readme
- **Privacy policy URL:** https://tankoup.com/en/legal/privacy-policy
- **Support contact:** info@tankoup.com
- **Icon:** `https://tankoup.com/icon.svg` (or the 180 px `apple-icon.png`)
- **Slug:** `tankoup` (permanent once published)

## 4. Use cases

- **Primary use cases:** finding the cheapest petrol station near a place in Spain; planning where to refuel on a road trip; comparing fuel prices across Spanish provinces; checking a station's prices and opening hours.
- **What users need before connecting:** nothing. No account, plan or setup.
- **Reads or writes:** reads only.

## 5. Company

- **Company:** TankoUp
- **Website:** https://tankoup.com
- **Primary contact:** _(Felipe fills this in the portal)_

## 6. Authentication

Authentication requirement: none.

## 7. Data handling

- Underlying API: our own (TankoUp's API, which serves the TankoUp apps and website). The price data is the Spanish government's open data.
- Personal health data: no. Sponsored content: no.

## 8. Test & launch

No test account is needed: the server has no sign-in. To test, add `https://mcp.tankoup.com/mcp` as a custom connector and ask, for example:

1. "Where is the cheapest diesel near Lucena, Córdoba?" → `find_cheapest_fuel_nearby`
2. "I'm driving from Madrid to Valencia. Where should I fill up with 95 petrol?" → `find_cheapest_fuel_on_route`
3. "How does diesel in Bizkaia compare with the rest of Spain?" → `get_province_fuel_prices`
4. "What are the opening hours and prices at the first station?" → `get_station_details`

Every tool was run in MCP Inspector and as a custom connector in Claude.

## 9. Compliance

Seven acknowledgments in the portal. Notes for each:

- Directory guidelines: read-only, narrow tools, accurate descriptions.
- First-party API usage: the server calls only TankoUp's own API.
- Financial transactions: none.
- AI media generation: none.
- Prompt injection: tool descriptions describe; none instructs the model. Tool results are data from our own API.
- Conversation data collection: none. The server logs tool name, protocol version and duration only.
- Public documentation: the GitHub README.
