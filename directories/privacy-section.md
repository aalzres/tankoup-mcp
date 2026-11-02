# Section to add to TankoUp's privacy policy

Both directories link to <https://tankoup.com/en/legal/privacy-policy>, which today covers the app and the website but not the MCP server. This is the section to add (tanko-web, `src/app/[locale]/legal/privacy-policy`), in every language the page has.

---

### TankoUp in AI assistants (MCP server)

TankoUp can be used from AI assistants such as Claude and ChatGPT through our MCP server at `mcp.tankoup.com`. When you ask one of them about fuel prices, the assistant sends our server the search it needs: a fuel type and a place name or coordinates, a route's start and end, a province, or a station.

- We use that search only to answer it. We do not store it, link it to you or use it for anything else.
- Our server logs which tool was called and how long it took. It does not log the places, coordinates or other details of the search.
- Like any web service, our hosting provider (Google Cloud) records the IP address that made each request, which is usually the assistant's and not yours, and deletes it after 30 days.
- We receive nothing else from the assistant: not your name, your account or your conversation.
- What the assistant itself does with your conversation is governed by its own privacy policy (Anthropic for Claude, OpenAI for ChatGPT).
