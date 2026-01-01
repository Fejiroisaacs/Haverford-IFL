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
