document.addEventListener("DOMContentLoaded", function () {

    // Ask for confirmation before any destructive form submit
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
        form.addEventListener("submit", function (e) {
            if (!window.confirm(form.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });

    // Mobile sidebar toggle
    const sidebar = document.getElementById("sidebar");
    const toggle = document.getElementById("sidebarToggle");
    if (sidebar && toggle) {
        toggle.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
        document.addEventListener("click", function (e) {
            if (window.innerWidth < 992 && sidebar.classList.contains("open")
                && !sidebar.contains(e.target) && e.target !== toggle) {
                sidebar.classList.remove("open");
            }
        });
    }

    // Instant client-side filtering for any table with data-filter-table
    document.querySelectorAll("input[data-filter-table]").forEach(function (input) {
        const table = document.getElementById(input.dataset.filterTable);
        if (!table) return;
        input.addEventListener("input", function () {
            const term = input.value.trim().toLowerCase();
            table.querySelectorAll("tbody tr").forEach(function (row) {
                row.style.display = row.textContent.toLowerCase().includes(term) ? "" : "none";
            });
        });
    });

    // Auto-dismiss flash alerts after 5 seconds
    document.querySelectorAll(".alert-dismissible").forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });
});
