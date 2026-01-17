// Index Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const bannerVersion = '3';
    const dismissedVersion = localStorage.getItem('featureBannerDismissedVersion');

    if (dismissedVersion !== bannerVersion) {
        document.getElementById('featureBanner').style.display = 'block';
    } else {
        document.getElementById('featureBanner').style.display = 'none';
    }
});

// Feature Announcement Banner Functions
function dismissBanner() {
    const banner = document.getElementById('featureBanner');
    const bannerVersion = '3';
    banner.style.animation = 'slideDown 0.5s ease-out reverse';
    setTimeout(() => {
        banner.style.display = 'none';
        localStorage.setItem('featureBannerDismissedVersion', bannerVersion);
    }, 300);
}

// What's New Modal Functions
function openWhatsNew() {
    document.getElementById('whatsNewModal').style.display = 'block';
    document.body.style.overflow = 'hidden'; // Prevent background scrolling
}

function closeWhatsNew() {
    document.getElementById('whatsNewModal').style.display = 'none';
    document.body.style.overflow = 'auto'; // Restore scrolling
}

// Close modal when clicking outside the content
window.onclick = function(event) {
    const modal = document.getElementById('whatsNewModal');
    if (event.target === modal) {
        closeWhatsNew();
    }
}

// Close modal with Escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const modal = document.getElementById('whatsNewModal');
        if (modal.style.display === 'block') {
            closeWhatsNew();
        }
    }
});

// Countdown Timer
function initCountdownTimer() {
    const container = document.getElementById('countdownContainer');
    if (!container) return;

    const dateStr = container.dataset.date;
    const timeStr = container.dataset.time;

    if (!dateStr) {
        container.style.display = 'none';
        return;
    }

    // Parse the date (format: "Sunday, January 19" or similar)
    const targetDate = parseMatchDate(dateStr, timeStr);
    if (!targetDate) {
        container.style.display = 'none';
        return;
    }

    // Update countdown every second
    updateCountdown(targetDate);
    setInterval(() => updateCountdown(targetDate), 1000);
}

function parseMatchDate(dateStr, timeStr) {
    try {
        // Parse date like "Sunday, January 19" or "January 19"
        const currentYear = new Date().getFullYear();

        // Remove day name if present (e.g., "Sunday, ")
        let cleanDate = dateStr.replace(/^\w+,\s*/, '');

        // Parse month and day
        const months = {
            'January': 0, 'February': 1, 'March': 2, 'April': 3,
            'May': 4, 'June': 5, 'July': 6, 'August': 7,
            'September': 8, 'October': 9, 'November': 10, 'December': 11
        };

        const parts = cleanDate.split(' ');
        const month = months[parts[0]];
        const day = parseInt(parts[1]);

        if (month === undefined || isNaN(day)) return null;

        // Parse time (format: "7:00 PM" or "19:00")
        let hours = 0, minutes = 0;
        if (timeStr) {
            const timeParts = timeStr.match(/(\d+):(\d+)\s*(AM|PM)?/i);
            if (timeParts) {
                hours = parseInt(timeParts[1]);
                minutes = parseInt(timeParts[2]);
                const period = timeParts[3];
                if (period) {
                    if (period.toUpperCase() === 'PM' && hours !== 12) hours += 12;
                    if (period.toUpperCase() === 'AM' && hours === 12) hours = 0;
                }
            }
        }

        let targetDate = new Date(currentYear, month, day, hours, minutes);

        // If the date has passed, assume it's next year
        if (targetDate < new Date()) {
            targetDate = new Date(currentYear + 1, month, day, hours, minutes);
        }

        return targetDate;
    } catch (e) {
        console.error('Error parsing match date:', e);
        return null;
    }
}

function updateCountdown(targetDate) {
    const now = new Date();
    const diff = targetDate - now;

    const daysEl = document.getElementById('countdownDays');
    const hoursEl = document.getElementById('countdownHours');
    const minutesEl = document.getElementById('countdownMinutes');
    const secondsEl = document.getElementById('countdownSeconds');
    const container = document.getElementById('countdownContainer');
    const timerEl = document.getElementById('countdownTimer');
    const labelEl = container.querySelector('.countdown-label');

    if (diff <= 0) {
        // Match has started or passed
        if (labelEl) labelEl.textContent = 'Match Started!';
        if (timerEl) timerEl.style.display = 'none';
        return;
    }

    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((diff % (1000 * 60)) / 1000);

    if (daysEl) daysEl.textContent = String(days).padStart(2, '0');
    if (hoursEl) hoursEl.textContent = String(hours).padStart(2, '0');
    if (minutesEl) minutesEl.textContent = String(minutes).padStart(2, '0');
    if (secondsEl) secondsEl.textContent = String(seconds).padStart(2, '0');
}

// Initialize countdown when DOM is ready
document.addEventListener('DOMContentLoaded', initCountdownTimer);
