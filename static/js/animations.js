// =====================================
// Premium Scroll Reveal Animation
// =====================================

const reveals = document.querySelectorAll(".reveal");

function revealOnScroll(){

    reveals.forEach(item=>{

        const top = item.getBoundingClientRect().top;

        const windowHeight = window.innerHeight;

        if(top < windowHeight - 120){

            item.classList.add("active");

        }

    });

}

window.addEventListener("scroll", revealOnScroll);

window.addEventListener("load", revealOnScroll);

// =====================================
// Luxury Mouse Glow
// =====================================

const glow = document.querySelector(".cursor-glow");

document.addEventListener("mousemove",(e)=>{

    glow.style.left = e.clientX + "px";

    glow.style.top = e.clientY + "px";

});

// =====================================
// Premium Animated Counters
// =====================================

const counters = document.querySelectorAll(".counter");

const animateCounters = () => {

    counters.forEach(counter => {

        if (counter.dataset.started) return;

        const rect = counter.getBoundingClientRect();

        if (rect.top > window.innerHeight - 100) return;

        counter.dataset.started = "true";

        const target = parseFloat(counter.dataset.target);

        const isDecimal = target % 1 !== 0;

        let current = 0;

        const step = target / 80;

        const update = () => {

            current += step;

            if (current >= target) {

                current = target;

            }

            if (isDecimal) {

                counter.textContent = current.toFixed(1) + "★";

            } else if (target >= 1000) {

                counter.textContent = Math.floor(current).toLocaleString() + "+";

            } else {

                counter.textContent = Math.floor(current) + "+";

            }

            if (current < target) {

                requestAnimationFrame(update);

            }

        };

        update();

    });

};

window.addEventListener("scroll", animateCounters);
window.addEventListener("load", animateCounters);

// =====================================
// Premium Preloader
// =====================================

window.addEventListener("load", () => {

    const preloader = document.getElementById("preloader");

    setTimeout(() => {

        preloader.classList.add("hide");

    }, 1200);

});

// =====================================
// Back To Top
// =====================================

const backToTop = document.getElementById("backToTop");

window.addEventListener("scroll", () => {

    if(window.scrollY > 400){

        backToTop.classList.add("show");

    }

    else{

        backToTop.classList.remove("show");

    }

});

backToTop.addEventListener("click", () => {

    window.scrollTo({

        top:0,

        behavior:"smooth"

    });

});