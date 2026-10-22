// Links the clause list and the highlighted text, and offers the JSON download.
// Document text is never inserted as HTML here; it arrives escaped from the server.
(function () {
  "use strict";

  function select(index, scrollList) {
    document.querySelectorAll(".active").forEach(function (el) {
      el.classList.remove("active");
    });
    var item = document.querySelector('.clause-item[data-clause="' + index + '"]');
    var span = document.getElementById("span-" + index);
    if (item) {
      item.classList.add("active");
      if (scrollList) item.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    if (span) {
      span.classList.add("active");
      if (!scrollList) span.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  document.querySelectorAll(".clause-item").forEach(function (item) {
    item.addEventListener("click", function () {
      select(item.dataset.clause, false);
    });
  });

  document.querySelectorAll("mark.span").forEach(function (span) {
    span.addEventListener("click", function () {
      select(span.dataset.clause, true);
    });
  });

  var download = document.getElementById("download-json");
  var data = document.getElementById("result-data");
  if (download && data) {
    download.addEventListener("click", function () {
      var result = JSON.parse(data.textContent);
      var blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = result.source.replace(/\.[^.]+$/, "") + ".clauses.json";
      link.click();
      URL.revokeObjectURL(link.href);
    });
  }
})();
