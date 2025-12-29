/**
 * IFL Gallery JavaScript
 *
 * Features:
 * - Season filtering with smooth animations
 * - Lightbox modal for full-size image viewing
 * - Keyboard navigation (arrow keys, escape)
 * - Touch gesture support for mobile
 * - Image preloading for better performance
 */

// Global state
let currentImageId = null;
let allImageIds = [];
let filteredImageIds = [];
let currentFilter = 'all';
let lightboxFocusTrap = null;

/**
 * Initialize gallery on page load
 */
document.addEventListener('DOMContentLoaded', function() {
    initializeGallery();
    setupEventListeners();
    setupKeyboardNavigation();
    setupTouchGestures();
});

/**
 * Initialize gallery data and state
 */
function initializeGallery() {
    // Build list of all image IDs
    allImageIds = [];
    const allTags = new Set();
    const allPlayers = new Set();

    if (window.galleryData && window.galleryData.seasons) {
        Object.keys(window.galleryData.seasons).forEach(seasonNum => {
            const season = window.galleryData.seasons[seasonNum];
            if (season.images && season.images.length > 0) {
                season.images.forEach(image => {
                    allImageIds.push(image.id);

                    // Collect tags
                    if (image.tags) {
                        image.tags.forEach(tag => allTags.add(tag));
                    }

                    // Collect players
                    if (image.players) {
                        image.players.forEach(player => allPlayers.add(player));
                    }
                });
            }
        });
    }

    filteredImageIds = [...allImageIds];
    updateImageCount();

    // Populate filter dropdowns
    populateTagFilter(Array.from(allTags).sort());
    populatePlayerFilter(Array.from(allPlayers).sort());
}

/**
 * Populate tag filter dropdown
 */
function populateTagFilter(tags) {
    const tagFilter = document.getElementById('tagFilter');
    if (!tagFilter) return;

    // Clear existing options except "All Tags"
    tagFilter.innerHTML = '<option value="all">All Tags</option>';

    tags.forEach(tag => {
        const option = document.createElement('option');
        option.value = tag;
        option.textContent = tag;
        tagFilter.appendChild(option);
    });
}

/**
 * Populate player filter dropdown
 */
function populatePlayerFilter(players) {
    const playerFilter = document.getElementById('playerFilter');
    if (!playerFilter) return;

    // Clear existing options except "All Players"
    playerFilter.innerHTML = '<option value="all">All Players</option>';

    players.forEach(player => {
        const option = document.createElement('option');
        option.value = player;
        option.textContent = player;
        playerFilter.appendChild(option);
    });
}

/**
 * Apply all filters (season, tag, player, search)
 */
function applyFilters() {
    const searchInput = document.getElementById('gallerySearch');
    const seasonFilter = document.getElementById('seasonFilter');
    const tagFilter = document.getElementById('tagFilter');
    const playerFilter = document.getElementById('playerFilter');

    const searchQuery = searchInput ? searchInput.value.toLowerCase().trim() : '';
    const selectedSeason = seasonFilter ? seasonFilter.value : 'all';
    const selectedTag = tagFilter ? tagFilter.value : 'all';
    const selectedPlayer = playerFilter ? playerFilter.value : 'all';

    const galleryItems = document.querySelectorAll('.gallery-item');
    const noResults = document.getElementById('noResults');
    const galleryGrid = document.getElementById('galleryGrid');

    let visibleCount = 0;
    filteredImageIds = [];

    // Show loading state
    if (galleryGrid) {
        galleryGrid.classList.add('loading');
    }

    // Add fade-out animation
    galleryItems.forEach(item => {
        item.classList.add('fade-out');
    });

    // Wait for fade-out, then filter
    setTimeout(() => {
        galleryItems.forEach(item => {
            const itemSeason = item.getAttribute('data-season');
            const imageId = item.getAttribute('data-image-id');
            const itemTags = item.getAttribute('data-tags') || '';
            const itemPlayers = item.getAttribute('data-players') || '';

            const imageData = getImageData(imageId);

            // Check all filter conditions
            let matchesSeason = selectedSeason === 'all' || itemSeason === selectedSeason;
            let matchesTag = selectedTag === 'all' || itemTags.split(',').includes(selectedTag);
            let matchesPlayer = selectedPlayer === 'all' || itemPlayers.split(',').includes(selectedPlayer);
            let matchesSearch = true;

            if (searchQuery && imageData) {
                const searchableText = [
                    imageData.caption || '',
                    imageData.match || '',
                    ...(imageData.tags || []),
                    ...(imageData.players || [])
                ].join(' ').toLowerCase();

                matchesSearch = searchableText.includes(searchQuery);
            }

            if (matchesSeason && matchesTag && matchesPlayer && matchesSearch) {
                item.classList.remove('hidden', 'fade-out');
                filteredImageIds.push(imageId);
                visibleCount++;
            } else {
                item.classList.add('hidden');
                item.classList.remove('fade-out');
            }
        });

        // Show/hide no results message
        if (visibleCount === 0) {
            galleryGrid.style.display = 'none';
            noResults.style.display = 'block';
        } else {
            galleryGrid.style.display = 'block';
            noResults.style.display = 'none';
        }

        // Remove loading state
        if (galleryGrid) {
            galleryGrid.classList.remove('loading');
        }

        updateImageCount();
    }, 300); // Match CSS transition duration
}

/**
 * Reset all filters
 */
function resetFilters() {
    const searchInput = document.getElementById('gallerySearch');
    const seasonFilter = document.getElementById('seasonFilter');
    const tagFilter = document.getElementById('tagFilter');
    const playerFilter = document.getElementById('playerFilter');
    const searchClear = document.getElementById('searchClear');

    if (searchInput) searchInput.value = '';
    if (seasonFilter) seasonFilter.value = 'all';
    if (tagFilter) tagFilter.value = 'all';
    if (playerFilter) playerFilter.value = 'all';
    if (searchClear) searchClear.style.display = 'none';

    applyFilters();
}

// Keep filterBySeason for backwards compatibility
function filterBySeason() {
    applyFilters();
}

/**
 * Update image count badge
 */
function updateImageCount() {
    const imageCount = document.getElementById('imageCount');
    if (imageCount) {
        const count = filteredImageIds.length;
        imageCount.textContent = `${count} image${count !== 1 ? 's' : ''}`;
    }
}

/**
 * Open lightbox with specified image or video
 */
function openLightbox(imageId) {
    currentImageId = imageId;

    // Get image/video data
    const imageData = getImageData(imageId);
    if (!imageData) {
        console.error('Item not found:', imageId);
        return;
    }

    // Get elements
    const lightbox = document.getElementById('lightbox');
    const lightboxImage = document.getElementById('lightboxImage');
    const lightboxVideo = document.getElementById('lightboxVideo');
    const youtubePlayer = document.getElementById('youtubePlayer');
    const lightboxSpinner = document.getElementById('lightboxSpinner');
    const spinnerText = document.getElementById('spinnerText');
    const lightboxCaption = document.getElementById('lightboxCaption');
    const lightboxMatch = document.getElementById('lightboxMatch');
    const lightboxSeason = document.getElementById('lightboxSeason');
    const lightboxDate = document.getElementById('lightboxDate');
    const lightboxTags = document.getElementById('lightboxTags');
    const lightboxPlayers = document.getElementById('lightboxPlayers');
    const downloadBtn = document.getElementById('downloadBtn');
    const currentImageNumber = document.getElementById('currentImageNumber');
    const totalImages = document.getElementById('totalImages');

    // Update counter
    const currentIndex = filteredImageIds.indexOf(imageId) + 1;
    currentImageNumber.textContent = currentIndex;
    totalImages.textContent = filteredImageIds.length;

    // Check if this is a video or image
    const isVideo = imageData.type === 'video';

    if (isVideo) {
        // Handle YouTube video

        // Show spinner while loading
        spinnerText.textContent = 'Loading video...';
        lightboxSpinner.classList.remove('hidden');

        // Hide image, show video container
        lightboxImage.style.display = 'none';
        lightboxVideo.style.display = 'block';

        // Add class to lightbox for video-specific styling
        lightbox.classList.add('showing-video');

        // Build YouTube embed URL with optional autoplay 
        // Users can enable autoplay by setting enableAutoplay to true
        const enableAutoplay = false; // Set to true to enable autoplay
        const autoplayParam = enableAutoplay ? 'autoplay=1' : 'autoplay=0';
        const youtubeUrl = `https://www.youtube.com/embed/${imageData.youtube_id}?${autoplayParam}&rel=0&modestbranding=1`;

        // Set iframe source
        youtubePlayer.src = youtubeUrl;

        // Hide spinner after a short delay (YouTube loads quickly)
        setTimeout(() => {
            lightboxSpinner.classList.add('hidden');
        }, 500);

        // Hide download button for videos
        downloadBtn.style.display = 'none';

    } else {
        // Handle regular image
        // Show spinner while loading
        spinnerText.textContent = 'Loading image...';
        lightboxSpinner.classList.remove('hidden');
        lightboxImage.style.opacity = '0';

        // Show image, hide video container
        lightboxImage.style.display = 'block';
        lightboxVideo.style.display = 'none';

        // Remove video class from lightbox
        lightbox.classList.remove('showing-video');

        // Clear video iframe to stop playback
        youtubePlayer.src = '';

        // Set image with loading handler
        const img = new Image();
        img.onload = function() {
            lightboxImage.src = imageData.full;
            lightboxImage.alt = imageData.alt;
            lightboxSpinner.classList.add('hidden');
            lightboxImage.style.opacity = '1';
            lightboxImage.style.transition = 'opacity 0.3s ease';
        };
        img.onerror = function() {
            lightboxImage.src = '/static/Images/Logo/logo.png';
            lightboxImage.alt = 'Image failed to load';
            lightboxSpinner.classList.add('hidden');
            lightboxImage.style.opacity = '1';
        };
        img.src = imageData.full;

        // Show and set download link
        downloadBtn.style.display = 'flex';
        downloadBtn.href = imageData.full;
        downloadBtn.download = `${imageId}.webp`;
    }

    // Set caption and match
    lightboxCaption.textContent = imageData.caption || 'Untitled';
    lightboxMatch.textContent = imageData.match || '';
    lightboxMatch.style.display = imageData.match ? 'block' : 'none';

    // Set metadata
    const seasonNum = getSeasonForImage(imageId);
    lightboxSeason.textContent = `Season ${seasonNum}`;
    lightboxDate.textContent = imageData.date || '';
    lightboxDate.style.display = imageData.date ? 'inline-block' : 'none';

    // Set tags
    lightboxTags.innerHTML = '';
    if (imageData.tags && imageData.tags.length > 0) {
        imageData.tags.forEach(tag => {
            const tagElement = document.createElement('span');
            tagElement.className = 'tag';
            tagElement.textContent = tag;
            lightboxTags.appendChild(tagElement);
        });
        lightboxTags.style.display = 'flex';
    } else {
        lightboxTags.style.display = 'none';
    }

    // Set players
    lightboxPlayers.innerHTML = '';
    if (imageData.players && imageData.players.length > 0) {
        imageData.players.forEach(player => {
            const playerElement = document.createElement('span');
            playerElement.className = 'player';
            playerElement.textContent = player;
            lightboxPlayers.appendChild(playerElement);
        });
        lightboxPlayers.style.display = 'flex';
    } else {
        lightboxPlayers.style.display = 'none';
    }

    // Show lightbox
    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden'; // Prevent background scrolling

    // Activate focus trap for accessibility
    if (!lightboxFocusTrap) {
        lightboxFocusTrap = new FocusTrap(lightbox);

        // Listen for escape key from focus trap
        lightbox.addEventListener('focustrap:escape', closeLightbox);
    }
    lightboxFocusTrap.activate();

    // Preload adjacent images
    preloadAdjacentImages(imageId);
}

/**
 * Close lightbox
 */
function closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    const youtubePlayer = document.getElementById('youtubePlayer');

    // Stop YouTube video playback by clearing iframe src
    if (youtubePlayer) {
        youtubePlayer.src = '';
    }

    lightbox.classList.remove('active', 'showing-video');
    document.body.style.overflow = ''; // Restore scrolling
    currentImageId = null;

    // Deactivate focus trap (this will restore focus automatically)
    if (lightboxFocusTrap) {
        lightboxFocusTrap.deactivate();
    }
}

/**
 * Navigate to previous or next image in lightbox
 */
function navigateLightbox(direction) {
    if (!currentImageId || filteredImageIds.length === 0) return;

    const currentIndex = filteredImageIds.indexOf(currentImageId);
    if (currentIndex === -1) return;

    let newIndex = currentIndex + direction;

    // Wrap around
    if (newIndex < 0) {
        newIndex = filteredImageIds.length - 1;
    } else if (newIndex >= filteredImageIds.length) {
        newIndex = 0;
    }

    const newImageId = filteredImageIds[newIndex];
    openLightbox(newImageId);
}

/**
 * Get image data by ID
 */
function getImageData(imageId) {
    if (!window.galleryData || !window.galleryData.seasons) return null;

    for (const seasonNum in window.galleryData.seasons) {
        const season = window.galleryData.seasons[seasonNum];
        if (season.images) {
            const image = season.images.find(img => img.id === imageId);
            if (image) return image;
        }
    }

    return null;
}

/**
 * Get season number for an image ID
 */
function getSeasonForImage(imageId) {
    if (!window.galleryData || !window.galleryData.seasons) return null;

    for (const seasonNum in window.galleryData.seasons) {
        const season = window.galleryData.seasons[seasonNum];
        if (season.images) {
            const found = season.images.find(img => img.id === imageId);
            if (found) return seasonNum;
        }
    }

    return null;
}

/**
 * Preload adjacent images for faster navigation (skip videos)
 */
function preloadAdjacentImages(imageId) {
    const currentIndex = filteredImageIds.indexOf(imageId);
    if (currentIndex === -1) return;

    // Preload previous and next images
    const indicesToPreload = [currentIndex - 1, currentIndex + 1];

    indicesToPreload.forEach(index => {
        // Handle wrapping
        let actualIndex = index;
        if (actualIndex < 0) {
            actualIndex = filteredImageIds.length - 1;
        } else if (actualIndex >= filteredImageIds.length) {
            actualIndex = 0;
        }

        const nextImageId = filteredImageIds[actualIndex];
        const imageData = getImageData(nextImageId);

        // Only preload images, not videos
        if (imageData && imageData.type !== 'video' && imageData.full) {
            const img = new Image();
            img.src = imageData.full;
        }
    });
}

/**
 * Setup keyboard navigation
 */
function setupKeyboardNavigation() {
    document.addEventListener('keydown', function(e) {
        const lightbox = document.getElementById('lightbox');

        // Only handle keyboard events when lightbox is active
        if (!lightbox.classList.contains('active')) return;

        switch(e.key) {
            case 'Escape':
                closeLightbox();
                break;
            case 'ArrowLeft':
                e.preventDefault();
                navigateLightbox(-1);
                break;
            case 'ArrowRight':
                e.preventDefault();
                navigateLightbox(1);
                break;
        }
    });
}

/**
 * Setup event listeners for gallery interactions
 */
function setupEventListeners() {
    // Image click handlers using event delegation
    const galleryGrid = document.getElementById('galleryGrid');
    if (galleryGrid) {
        galleryGrid.addEventListener('click', function(e) {
            const thumbnail = e.target.closest('.gallery-thumbnail');
            if (thumbnail) {
                const imageId = thumbnail.getAttribute('data-lightbox-image');
                if (imageId) {
                    openLightbox(imageId);
                }
            }
        });
    }

    // Search input
    const searchInput = document.getElementById('gallerySearch');
    const searchClear = document.getElementById('searchClear');

    if (searchInput) {
        searchInput.addEventListener('input', function(e) {
            const value = e.target.value;

            // Show/hide clear button
            if (searchClear) {
                searchClear.style.display = value ? 'block' : 'none';
            }

            // Apply filters with debouncing
            clearTimeout(window.searchTimeout);
            window.searchTimeout = setTimeout(() => {
                applyFilters();
            }, 300);
        });
    }

    if (searchClear) {
        searchClear.addEventListener('click', function() {
            if (searchInput) {
                searchInput.value = '';
                searchClear.style.display = 'none';
                applyFilters();
            }
        });
    }

    // Season filter change
    const seasonFilter = document.getElementById('seasonFilter');
    if (seasonFilter) {
        seasonFilter.addEventListener('change', applyFilters);
    }

    // Tag filter change
    const tagFilter = document.getElementById('tagFilter');
    if (tagFilter) {
        tagFilter.addEventListener('change', applyFilters);
    }

    // Player filter change
    const playerFilter = document.getElementById('playerFilter');
    if (playerFilter) {
        playerFilter.addEventListener('change', applyFilters);
    }

    // Reset filters button
    const resetFiltersBtn = document.getElementById('resetFilters');
    if (resetFiltersBtn) {
        resetFiltersBtn.addEventListener('click', resetFilters);
    }

    // Lightbox close button
    const lightboxClose = document.querySelector('.lightbox-close');
    if (lightboxClose) {
        lightboxClose.addEventListener('click', closeLightbox);
    }

    // Lightbox background click to close
    const lightbox = document.getElementById('lightbox');
    if (lightbox) {
        lightbox.addEventListener('click', function(e) {
            if (e.target === lightbox) {
                closeLightbox();
            }
        });
    }

    // Prevent lightbox from closing when clicking content
    const lightboxContent = document.querySelector('.lightbox-content');
    if (lightboxContent) {
        lightboxContent.addEventListener('click', function(e) {
            e.stopPropagation();
        });
    }

    // Lightbox navigation buttons
    const prevBtn = document.querySelector('.lightbox-prev');
    const nextBtn = document.querySelector('.lightbox-next');

    if (prevBtn) {
        prevBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            navigateLightbox(-1);
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            navigateLightbox(1);
        });
    }

}

/**
 * Setup touch gestures for mobile
 */
function setupTouchGestures() {
    let touchStartX = 0;
    let touchEndX = 0;

    const lightbox = document.getElementById('lightbox');

    lightbox.addEventListener('touchstart', function(e) {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });

    lightbox.addEventListener('touchend', function(e) {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, { passive: true });

    function handleSwipe() {
        const swipeThreshold = 50; // Minimum distance for a swipe
        const diff = touchStartX - touchEndX;

        if (Math.abs(diff) > swipeThreshold) {
            if (diff > 0) {
                // Swipe left - next image
                navigateLightbox(1);
            } else {
                // Swipe right - previous image
                navigateLightbox(-1);
            }
        }
    }
}

/**
 * Search/filter images by text (optional enhancement)
 */
function searchImages(query) {
    const lowerQuery = query.toLowerCase().trim();

    if (!lowerQuery) {
        // Reset to current season filter
        filterBySeason();
        return;
    }

    const galleryItems = document.querySelectorAll('.gallery-item');
    const noResults = document.getElementById('noResults');
    const galleryGrid = document.getElementById('galleryGrid');

    let visibleCount = 0;
    filteredImageIds = [];

    galleryItems.forEach(item => {
        const imageId = item.getAttribute('data-image-id');
        const imageData = getImageData(imageId);

        if (!imageData) return;

        // Search in caption, match, tags, and players
        const searchableText = [
            imageData.caption || '',
            imageData.match || '',
            ...(imageData.tags || []),
            ...(imageData.players || [])
        ].join(' ').toLowerCase();

        if (searchableText.includes(lowerQuery)) {
            item.classList.remove('hidden');
            filteredImageIds.push(imageId);
            visibleCount++;
        } else {
            item.classList.add('hidden');
        }
    });

    // Show/hide no results message
    if (visibleCount === 0) {
        galleryGrid.style.display = 'none';
        noResults.style.display = 'block';
    } else {
        galleryGrid.style.display = 'block';
        noResults.style.display = 'none';
    }

    updateImageCount();
}

/**
 * Lazy load images when they come into viewport
 * (Native lazy loading is used in HTML, but this provides fallback/additional features)
 */
function setupLazyLoading() {
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('loading');
                    observer.unobserve(img);
                }
            });
        });

        const lazyImages = document.querySelectorAll('img[data-src]');
        lazyImages.forEach(img => imageObserver.observe(img));
    }
}

// Export functions for use in HTML onclick handlers
window.filterBySeason = filterBySeason;
window.openLightbox = openLightbox;
window.closeLightbox = closeLightbox;
window.navigateLightbox = navigateLightbox;
window.searchImages = searchImages;