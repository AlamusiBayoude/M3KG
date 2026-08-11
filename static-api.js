(() => {
  const nativeFetch = window.fetch.bind(window);
  const cache = new Map();
  const indexPromise = nativeFetch(new URL("data/site-index.json", document.baseURI)).then((response) => {
    if (!response.ok) throw new Error(`Static index HTTP ${response.status}`);
    return response.json();
  });

  const jsonResponse = (payload, status = 200) => new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
  const numberParam = (url, key, fallback, minimum, maximum) => {
    const value = Number(url.searchParams.get(key));
    return Number.isFinite(value) ? Math.max(minimum, Math.min(maximum, value)) : fallback;
  };
  const includesText = (value, query) => String(value || "").toLowerCase().includes(query);
  const loadShard = async (materialId) => {
    if (!cache.has(materialId)) {
      cache.set(materialId, nativeFetch(new URL(`data/materials/${encodeURIComponent(materialId)}.json`, document.baseURI)).then((response) => {
        if (!response.ok) throw new Error(`Material not found: ${materialId}`);
        return response.json();
      }));
    }
    return cache.get(materialId);
  };

  async function route(url) {
    const index = await indexPromise;
    const path = url.pathname;
    if (path === "/api/stats") return index.stats;
    if (path === "/api/materials") {
      const query = (url.searchParams.get("query") || "").trim().toLowerCase();
      const termCategory = url.searchParams.get("term_category") || "";
      const propertyClass = url.searchParams.get("property_class") || "";
      const sourceType = url.searchParams.get("source_type") || "";
      const kingdom = url.searchParams.get("kingdom") || "";
      const limit = numberParam(url, "limit", 24, 1, 100);
      const offset = numberParam(url, "offset", 0, 0, 100000);
      const filtered = index.materials.filter((item) =>
        (!query || includesText(item._search, query)) &&
        (!termCategory || item._term_categories.includes(termCategory)) &&
        (!propertyClass || item._property_classes.includes(propertyClass)) &&
        (!sourceType || item._source_types.includes(sourceType)) &&
        (!kingdom || item._kingdoms.includes(kingdom))
      );
      return { total: filtered.length, limit, offset, items: filtered.slice(offset, offset + limit) };
    }
    if (path.startsWith("/api/materials/")) {
      const requested = decodeURIComponent(path.split("/").pop());
      const materialId = index.material_lookup[requested] || requested;
      return (await loadShard(materialId)).detail;
    }
    if (path.startsWith("/api/graph/")) {
      const requested = decodeURIComponent(path.split("/").pop());
      const materialId = index.material_lookup[requested] || requested;
      return (await loadShard(materialId)).graph;
    }
    if (path === "/api/compare") {
      const ids = (url.searchParams.get("ids") || "").split(",").filter(Boolean).slice(0, 30);
      const items = [];
      const missing = [];
      for (const requested of ids) {
        const materialId = index.material_lookup[requested] || requested;
        try { items.push((await loadShard(materialId)).detail); } catch { missing.push(requested); }
      }
      return { limit: 30, items, missing };
    }
    if (path === "/api/search") {
      const query = (url.searchParams.get("query") || "").trim().toLowerCase();
      const docType = url.searchParams.get("type") || "all";
      const limit = numberParam(url, "limit", 20, 1, 100);
      if (!query) return { items: [] };
      const allowed = docType === "all" ? new Set(["material", "terminology", "origin"]) : new Set([docType]);
      const items = index.search_documents.filter((item) => allowed.has(item.doc_type) && includesText(item._search, query)).slice(0, limit)
        .map(({ _search, body, ...item }) => ({ ...item, snippet: String(body || "").slice(0, 260) }));
      return { items };
    }
    if (path === "/api/triples") return { items: [] };
    throw new Error(`Static API endpoint not found: ${path}`);
  }

  window.fetch = async (input, init) => {
    const raw = typeof input === "string" || input instanceof URL ? input : input.url;
    const url = new URL(raw, window.location.href);
    if (!url.pathname.startsWith("/api/")) return nativeFetch(input, init);
    try { return jsonResponse(await route(url)); }
    catch (error) { return jsonResponse({ error: error.message }, 404); }
  };
})();
