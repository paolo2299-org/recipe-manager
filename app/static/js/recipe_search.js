(function () {
    const input = document.getElementById("recipe-search");
    if (!input) return;

    const grid = document.querySelector(".recipe-grid");
    const cards = grid ? Array.from(grid.querySelectorAll("article[data-search]")) : [];
    const empty = document.getElementById("recipe-search-empty");
    const count = document.getElementById("recipe-count");
    const originalCountText = count ? count.textContent : null;

    function apply() {
        const query = input.value.trim().toLowerCase();
        const tokens = query ? query.split(/\s+/) : [];
        let visible = 0;

        for (const card of cards) {
            const haystack = card.dataset.search || "";
            const match = tokens.every((t) => haystack.includes(t));
            card.hidden = !match;
            if (match) visible++;
        }

        if (empty) empty.hidden = visible !== 0;

        if (count) {
            if (tokens.length === 0) {
                count.textContent = originalCountText;
            } else {
                count.textContent = `${visible} matching recipe${visible === 1 ? "" : "s"}`;
            }
        }
    }

    input.addEventListener("input", apply);
})();
