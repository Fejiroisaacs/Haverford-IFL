/**
 * Focus Trap Utility
 * Keeps keyboard focus within a modal/dialog when it's open
 * Improves accessibility for keyboard users
 */

class FocusTrap {
    constructor(element) {
        this.element = element;
        this.firstFocusableElement = null;
        this.lastFocusableElement = null;
        this.previouslyFocusedElement = null;
        this.isActive = false;

        // Bind methods
        this.handleTabKey = this.handleTabKey.bind(this);
        this.handleEscape = this.handleEscape.bind(this);
    }

    /**
     * Get all focusable elements within the container
     */
    getFocusableElements() {
        const focusableSelectors = [
            'a[href]',
            'button:not([disabled])',
            'textarea:not([disabled])',
            'input:not([disabled])',
            'select:not([disabled])',
            '[tabindex]:not([tabindex="-1"])'
        ].join(', ');

        return Array.from(this.element.querySelectorAll(focusableSelectors))
            .filter(el => {
                // Filter out hidden elements
                return el.offsetParent !== null &&
                       getComputedStyle(el).visibility !== 'hidden';
            });
    }

    /**
     * Handle Tab key press to trap focus
     */
    handleTabKey(e) {
        if (e.key !== 'Tab' || !this.isActive) return;

        const focusableElements = this.getFocusableElements();

        if (focusableElements.length === 0) {
            e.preventDefault();
            return;
        }

        this.firstFocusableElement = focusableElements[0];
        this.lastFocusableElement = focusableElements[focusableElements.length - 1];

        // Shift + Tab (backwards)
        if (e.shiftKey) {
            if (document.activeElement === this.firstFocusableElement) {
                e.preventDefault();
                this.lastFocusableElement.focus();
            }
        }
        // Tab (forwards)
        else {
            if (document.activeElement === this.lastFocusableElement) {
                e.preventDefault();
                this.firstFocusableElement.focus();
            }
        }
    }

    /**
     * Handle Escape key to close modal
     */
    handleEscape(e) {
        if (e.key === 'Escape' && this.isActive) {
            // Dispatch custom event that can be caught by modal close handlers
            const event = new CustomEvent('focustrap:escape', {
                detail: { trap: this }
            });
            this.element.dispatchEvent(event);
        }
    }

    /**
     * Activate the focus trap
     */
    activate() {
        if (this.isActive) return;

        // Store currently focused element to restore later
        this.previouslyFocusedElement = document.activeElement;

        // Add event listeners
        document.addEventListener('keydown', this.handleTabKey);
        document.addEventListener('keydown', this.handleEscape);

        this.isActive = true;

        // Focus first focusable element after a short delay
        setTimeout(() => {
            const focusableElements = this.getFocusableElements();
            if (focusableElements.length > 0) {
                focusableElements[0].focus();
            }
        }, 50);
    }

    /**
     * Deactivate the focus trap
     */
    deactivate() {
        if (!this.isActive) return;

        // Remove event listeners
        document.removeEventListener('keydown', this.handleTabKey);
        document.removeEventListener('keydown', this.handleEscape);

        this.isActive = false;

        // Restore focus to previously focused element
        if (this.previouslyFocusedElement && this.previouslyFocusedElement.focus) {
            setTimeout(() => {
                this.previouslyFocusedElement.focus();
            }, 50);
        }
    }

    /**
     * Check if trap is active
     */
    get active() {
        return this.isActive;
    }
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FocusTrap;
}

// Make available globally
window.FocusTrap = FocusTrap;
