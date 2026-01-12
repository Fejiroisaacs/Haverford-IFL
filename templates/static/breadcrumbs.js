/**
 * Breadcrumb Navigation Generator
 * Automatically creates breadcrumb navigation based on the current URL path
 */

class BreadcrumbGenerator {
    constructor() {
        this.pathMappings = {
            'home': { name: 'Home', icon: 'fa-home' },
            'index': { name: 'Home', icon: 'fa-home' },
            'matches': { name: 'Matches', icon: 'fa-futbol' },
            'teams': { name: 'Teams', icon: 'fa-users' },
            'players': { name: 'Players', icon: 'fa-user-friends' },
            'statistics': { name: 'Statistics', icon: 'fa-chart-bar' },
            'gallery': { name: 'Gallery', icon: 'fa-images' },
            'contact': { name: 'Contact', icon: 'fa-envelope' },
            'fantasy': { name: 'Fantasy League', icon: 'fa-trophy' },
            'settings': { name: 'Settings', icon: 'fa-cog' },
            'login': { name: 'Login', icon: 'fa-sign-in-alt' },
            'signup': { name: 'Sign Up', icon: 'fa-user-plus' },
            'hall-of-fame': { name: 'Hall of Fame', icon: 'fa-medal' },
            'archives': { name: 'Season Archives', icon: 'fa-archive' },
            'admin': { name: 'Admin', icon: 'fa-shield-alt' },
            'patch-notes': { name: 'Patch Notes', icon: 'fa-clipboard-list' }
        };
    }

    /**
     * Generate breadcrumb HTML for current page
     * @param {string} customPath - Optional custom path override
     * @returns {string} HTML string for breadcrumbs
     */
    generate(customPath = null) {
        const path = customPath || window.location.pathname;
        const segments = path.split('/').filter(seg => seg !== '');

        // Root page (home)
        if (segments.length === 0 || segments[0] === 'index') {
            return ''; // No breadcrumbs on home page
        }

        let breadcrumbHTML = '<nav class="breadcrumb-container" aria-label="Breadcrumb"><ol class="breadcrumb">';

        // Always start with home
        breadcrumbHTML += `
            <li class="breadcrumb-item">
                <a href="/">
                    <i class="fas fa-home"></i>
                    <span>Home</span>
                </a>
            </li>
        `;

        // Build path progressively
        let currentPath = '';

        segments.forEach((segment, index) => {
            currentPath += '/' + segment;
            const isLast = index === segments.length - 1;
            const mapping = this.pathMappings[segment.toLowerCase()];

            // Determine display name
            let displayName;
            let icon = 'fa-folder';

            if (mapping) {
                displayName = mapping.name;
                icon = mapping.icon;
            } else {
                // Try to prettify the segment
                displayName = this.prettifySegment(segment);
            }

            // Add separator
            breadcrumbHTML += '<li class="breadcrumb-separator" aria-hidden="true">/</li>';

            if (isLast) {
                // Last item (current page) - not a link
                breadcrumbHTML += `
                    <li class="breadcrumb-item active" aria-current="page">
                        ${displayName}
                    </li>
                `;
            } else {
                // Intermediate item - make it a link
                breadcrumbHTML += `
                    <li class="breadcrumb-item">
                        <a href="${currentPath}">
                            <i class="fas ${icon}"></i>
                            <span>${displayName}</span>
                        </a>
                    </li>
                `;
            }
        });

        breadcrumbHTML += '</ol></nav>';
        return breadcrumbHTML;
    }

    /**
     * Prettify a URL segment for display
     * @param {string} segment - URL segment
     * @returns {string} Prettified name
     */
    prettifySegment(segment) {
        // Decode URI component
        segment = decodeURIComponent(segment);

        // Replace hyphens and underscores with spaces
        segment = segment.replace(/[-_]/g, ' ');

        // Capitalize each word
        segment = segment.replace(/\b\w/g, char => char.toUpperCase());

        return segment;
    }

    /**
     * Insert breadcrumb into the page
     * @param {string} selector - CSS selector for container element
     * @param {string} customPath - Optional custom path override
     */
    insertInto(selector, customPath = null) {
        const container = document.querySelector(selector);
        if (container) {
            const breadcrumbHTML = this.generate(customPath);
            if (breadcrumbHTML) {
                container.innerHTML = breadcrumbHTML + container.innerHTML;
            }
        }
    }

    /**
     * Auto-initialize breadcrumbs on elements with data-breadcrumb attribute
     */
    autoInit() {
        document.addEventListener('DOMContentLoaded', () => {
            const elements = document.querySelectorAll('[data-breadcrumb]');
            elements.forEach(element => {
                const customPath = element.getAttribute('data-breadcrumb-path');
                const breadcrumbHTML = this.generate(customPath);
                if (breadcrumbHTML) {
                    element.insertAdjacentHTML('afterbegin', breadcrumbHTML);
                }
            });
        });
    }
}

// Create global instance
window.breadcrumbGenerator = new BreadcrumbGenerator();

// Auto-initialize
window.breadcrumbGenerator.autoInit();
