window.addEventListener('scroll', function() {
    let header = document.querySelector('header');
    let windowPosition = window.scrollY > 0;
    header.classList.toggle('scrolling-active', windowPosition);
});

// Navigation functions
function openNav() {
    document.getElementById("myNav").style.width = "100%";
}

function closeNav() {
    document.getElementById("myNav").style.width = "0%";
}

function openMobileNav() {
    document.getElementById("mySidenav").style.width = "250px";
    document.getElementById("navIcon").style.display = "None";
}

function closeMobileNav() {
    document.getElementById("mySidenav").style.width = "0";
    document.getElementById("navIcon").style.display = "Block";
}