// Restored advanced chatbot script (cleaned and fixed)
// Premium AI Chatbot - Advanced features restored with fixes

// =========================================
// Elements (will be initialized on DOMContentLoaded)
// =========================================

let chatToggle;
let chatContainer;
let closeChat;
let sendButton;
let userInput;
let chatBody;
let typingIndicator;

let chatOpen = false;

// Note: DOM event listeners and element bindings are attached
// inside `initChat()` once the DOM is ready to avoid null
// references when the script is loaded in <head>.

function initChat(){

	// Query elements
	chatToggle = document.getElementById("chat-toggle");
	chatContainer = document.getElementById("chat-container");
	closeChat = document.getElementById("close-chat");
	sendButton = document.getElementById("send-message");
	userInput = document.getElementById("user-message");
	chatBody = document.getElementById("chat-body");
	typingIndicator = document.getElementById("typing-indicator");

	if(!chatToggle || !chatContainer) return;

	// If elements are positioned using right/bottom in CSS, convert to left/top
	function convertRightBottomToLeftTop(el){

		try{
			const style = window.getComputedStyle(el);
			let rect = el.getBoundingClientRect();
			let width = rect.width || parseFloat(style.width) || 0;
			let height = rect.height || parseFloat(style.height) || 0;
			const wasHidden = style.display === 'none' || width === 0 || height === 0;

			if(wasHidden){
				const originalDisplay = el.style.display;
				const originalVisibility = el.style.visibility;
				el.style.visibility = 'hidden';
				el.style.display = 'block';
				rect = el.getBoundingClientRect();
				width = rect.width || width;
				height = rect.height || height;
				el.style.display = originalDisplay;
				el.style.visibility = originalVisibility;
			}

			let left = rect.left;
			let top = rect.top;

			if(style.right && style.right !== 'auto'){
				const right = parseFloat(style.right);
				left = window.innerWidth - right - width;
				el.style.left = left + 'px';
				el.style.right = 'auto';
			}

			if(style.bottom && style.bottom !== 'auto'){
				const bottom = parseFloat(style.bottom);
				top = window.innerHeight - bottom - height;
				el.style.top = top + 'px';
				el.style.bottom = 'auto';
			}
		}catch(e){ console.error('convertRightBottomToLeftTop failed', e); }

	}

	convertRightBottomToLeftTop(chatToggle);
	convertRightBottomToLeftTop(chatContainer);

	function positionChatContainerNearToggle(){
		if(!chatToggle || !chatContainer) return;
		const toggleRect = chatToggle.getBoundingClientRect();

		let containerRect = chatContainer.getBoundingClientRect();
		let restoredDisplay = null;
		let restoredVisibility = null;

		if(containerRect.width === 0 || containerRect.height === 0){
			restoredDisplay = chatContainer.style.display;
			restoredVisibility = chatContainer.style.visibility;
			chatContainer.style.visibility = 'hidden';
			chatContainer.style.display = 'flex';
			containerRect = chatContainer.getBoundingClientRect();
			chatContainer.style.display = restoredDisplay;
			chatContainer.style.visibility = restoredVisibility;
		}

		const gap = 8;
		const spaceAbove = toggleRect.top - gap - 10;
		const spaceBelow = window.innerHeight - toggleRect.bottom - gap - 10;
		let top;

		if(containerRect.height === 0){
			top = toggleRect.top - 540 - gap;
		} else if(containerRect.height <= spaceAbove || spaceAbove >= spaceBelow) {
			top = toggleRect.top - containerRect.height - gap;
		} else {
			top = toggleRect.bottom + gap;
		}

		let left = toggleRect.right - containerRect.width;
		if(left < 10) left = 10;
		if(left + containerRect.width > window.innerWidth - 10){
			left = window.innerWidth - containerRect.width - 10;
		}
		chatContainer.style.position = 'fixed';
		chatContainer.style.left = left + 'px';
		chatContainer.style.top = top + 'px';
		chatContainer.style.right = 'auto';
		chatContainer.style.bottom = 'auto';
	}

	// Open / toggle chat
	chatToggle.addEventListener("click", () => {

		try{
			chatToggle.style.zIndex = 99999;
			chatContainer.style.zIndex = 99998;
		}catch(e){}

		if (chatOpen) {
			closeChatWindow();
			return;
		}

		chatContainer.style.display = "flex";
		chatContainer.style.visibility = "hidden";
		chatContainer.style.opacity = "0";
		chatContainer.style.transform = "translateY(40px) scale(.92)";

		requestAnimationFrame(() => {
			positionChatContainerNearToggle();
			chatContainer.style.visibility = "visible";
			requestAnimationFrame(() => {
				chatContainer.style.transition = ".35s ease";
				chatContainer.style.opacity = "1";
				chatContainer.style.transform = "translateY(0) scale(1)";
				scrollToBottom();
			});

			chatOpen = true;

			// Clicking should also focus input after open
			setTimeout(()=>{ if(userInput) userInput.focus(); }, 360);
		});
	});

	function closeChatWindow(){
		if(!chatContainer) return;
		chatContainer.style.opacity = "0";
		chatContainer.style.transform = "translateY(40px) scale(.92)";
		setTimeout(()=>{
			if(chatContainer) chatContainer.style.display = "none";
		}, 300);
		chatOpen = false;
	}

	// Close button
	if(closeChat) closeChat.addEventListener("click", closeChatWindow);

	// Close when clicking outside
	document.addEventListener("click", function(e){
		if(chatOpen && !chatContainer.contains(e.target) && !chatToggle.contains(e.target)){
			closeChatWindow();
		}
	});

	// Enter -> send (use keydown for reliable detection)
	if(userInput) userInput.addEventListener("keydown", function(e){
		if(e.key === "Enter"){
			e.preventDefault();
			sendMessage();
		}
	});

	// Input enable/disable send
	if(userInput){
		userInput.addEventListener("input", ()=>{
			if(sendButton) sendButton.disabled = !userInput.value.trim();
		});
	}

	// Send button click
	if(sendButton) {
		sendButton.type = 'button';
		sendButton.addEventListener("click", ()=> sendMessage());
		if(userInput && !userInput.value.trim()) sendButton.disabled = true;
	}

	// Quick buttons
	document.querySelectorAll(".quick-btn").forEach(button=>{
		button.addEventListener("click", ()=>{
			const text = button.dataset.message || button.innerText || "";
			if(userInput) userInput.value = text;
			sendMessage();
		});
	});

	// Remove notification on open
	chatToggle.addEventListener("click", ()=>{ removeNotification(); });

	// Focus input after transition
	if(chatContainer) chatContainer.addEventListener("transitionend", ()=>{ if(chatOpen && userInput) userInput.focus(); });

	// Make draggable
	makeDraggable(chatToggle);
	makeDraggable(chatContainer);

	// Load history after successful initialization
	try{ if(typeof loadChatHistory === 'function') loadChatHistory(); }catch(e){ console.error('loadChatHistory error', e); }


}

// =========================================
// Time
// =========================================

function getCurrentTime(){

	const now = new Date();

	return now.toLocaleTimeString([],{

		hour:"2-digit",

		minute:"2-digit"

	});

}

// =========================================
// STEP 6.1
// Advanced Markdown Formatter
// =========================================

function formatMessage(text){

    if(!text){
        return "";
    }

    // Escape all raw HTML first
    let formatted = escapeHTML(String(text));

    // Bold
    formatted = formatted.replace(
        /\*\*(.*?)\*\*/g,
        "<strong>$1</strong>"
    );

    // Italic
    formatted = formatted.replace(
        /\*(.*?)\*/g,
        "<em>$1</em>"
    );

    // Bullet lists
    formatted = formatted.replace(
        /^\s*[-•]\s+(.*)$/gm,
        "<li>$1</li>"
    );

    formatted = formatted.replace(
        /(<li>.*?<\/li>)/gs,
        "<ul>$1</ul>"
    );

    // Number lists
    formatted = formatted.replace(
        /^\s*\d+\.\s+(.*)$/gm,
        "<li class=\"numbered\">$1</li>"
    );

    formatted = formatted.replace(
        /(?:<li class=\"numbered\">.*?<\/li>\s*)+/gs,
        match => "<ol>" + match + "</ol>"
    );

    formatted = formatted.replace(
        / class=\"numbered\"/g,
        ""
    );

    // Line breaks
    formatted = formatted.replace(
        /\n/g,
        "<br>"
    );

    return formatted;
}

// =========================================
// Auto Scroll
// =========================================

function scrollToBottom(){

	chatBody.scrollTop =
		chatBody.scrollHeight;

}

// =========================================
// STEP 5.1
// AI Typewriter Effect
// =========================================
function typeWriter(
	element,
	text,
	speed=15
){

	element.innerHTML = "";

	let index = 0;

	function type(){

		if(index < text.length){

			element.innerHTML =
				text.substring(
					0,
					index + 1
				);

			scrollToBottom();

			index++;

			setTimeout(
				type,
				speed
			);

		}

	}

	type();

}

// =========================================
// Add Message
// =========================================

function addMessage(
	message,
	sender="bot",
	typing=false
){

	if(!chatBody){
		try{ initChat(); }catch(e){ }
		if(!chatBody){ return; }
	}

	const messageWrapper =
		document.createElement("div");

	messageWrapper.className =
		"message " +
		(
			sender==="user"
			?
			"user-message"
			:
			"bot-message"
		);

	const bubble = document.createElement("p");

	messageWrapper.appendChild(
		bubble
	);

	chatBody.appendChild(
		messageWrapper
	);

	scrollToBottom();

	if(sender==="user"){

		bubble.innerHTML =
			formatMessage(message);

		return;

	}

	if(typing){

		typeWriter(

			bubble,

			formatMessage(message),

			15

		);

	}

	else{

		bubble.innerHTML =
			formatMessage(message);

	}

	scrollToBottom();

}

// =========================================
// Typing Indicator
// =========================================

function showTyping(){

	if(!typingIndicator)
		return;

	typingIndicator.style.display =
		"flex";

	scrollToBottom();

}

function hideTyping(){

	if(!typingIndicator)
		return;

	typingIndicator.style.display =
		"none";

}

// =========================================
// Send Message
// =========================================

async function sendMessage(){

	const message =
		userInput.value.trim();

	if(!message) {
		return;
	}

	addMessage(

		message,

		"user"

	);

	userInput.value="";

	sendButton.disabled=true;

	showTyping();

	try{

		const response =
			await fetch(
				"/chatbot/api/",
				{

					method:"POST",

					headers:{

						"Content-Type":
						"application/json"

					},

					body:JSON.stringify({

						message:message

					})

				}

			);

		const data =
			await response.json();

		hideTyping();

		const botReply =
			 data.reply ||
			 data.response ||
			 data.message ||
			"Sorry, I could not understand that.";

		addMessage(
		   botReply,
		   "bot",
		   true
		);

	}

	catch(error){

		console.error(
			"Chat Error:",
			error
		);

		hideTyping();

		addMessage(

			"⚠️ Unable to connect to AI service right now.",

			"bot",

			true

		);

	}

	sendButton.disabled=false;

}

// Quick Action Buttons are attached in initChat()

// =========================================
// (Removed JS welcome block to avoid duplicate with HTML welcome)
// =========================================

// =========================================
// Notification Handling
// =========================================

function showNotification(){

	const notification =
		document.querySelector(
			".chat-notification"
		);

	if(notification){

		notification.style.display =
			"block";

	}

}

function removeNotification(){

	const notification =
		document.querySelector(
			".chat-notification"
		);

	if(notification){

		notification.style.display =
			"none";

	}

}

// Notification removal on open is attached in initChat()

// Smooth input focus is handled inside initChat()

// Prevent empty spam handled inside initChat()

// =========================================
// STEP 6.2
// Advanced Message Enhancement Helpers
// =========================================

// Convert simple markdown links
function convertLinks(text){

    return text.replace(
        /\[(.*?)\]\((https?:\/\/[^\s)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
    );

}

// Escape unsafe HTML
function escapeHTML(text){

	return text

	.replace(
		/&/g,
		"&amp;"
	)

	.replace(
		/</g,
		"&lt;"
	)

	.replace(
		/>/g,
		"&gt;"
	)

	.replace(
		/"/g,
		"&quot;"
	)

	.replace(
		/'/g,
		"&#039;"
	);

}

// =========================================
// Upgrade formatMessage
// =========================================

const originalFormatMessage =
	formatMessage;

formatMessage = function(text){

	if(!text){

		return "";

	}

	let formatted =
		text;

	// Convert links first

	formatted =
		convertLinks(
			formatted
		);

	// Code blocks
	formatted = formatted.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");

	// Inline code

	formatted =
		formatted.replace(

			/`(.*?)`/g,

			"<code>$1</code>"

		);

	// Emoji spacing (safer unicode range)

	formatted =
	formatted.replace(

		 /([\u{1F300}-\u{1FAFF}])/gu,

		 " $1 "

	);

	// Restore previous formatter

	formatted =
		originalFormatMessage(
			formatted
		);

	return formatted;

};

// =========================================
// Chat History Support
// =========================================

function saveChatMessage(
	message,
	sender
){

	let history =
		JSON.parse(
			localStorage.getItem("chat_history")
		) || [];

	history.push({

		message: message,

		sender: sender,

		time: getCurrentTime()

	});

	// =====================================
	// Keep only the latest 30 messages
	// =====================================

	if(history.length > 30){

		history = history.slice(-30);

	}

	localStorage.setItem(

		"chat_history",

		JSON.stringify(history)

	);

}

function loadChatHistory(){

	let history =
		JSON.parse(

			localStorage.getItem(
				"chat_history"
			)

		)
		||
		[];

	history.forEach(item=>{

		addMessage(

			item.message,

			item.sender,

			false

		);

	});

}

// =========================================
// Override Add Message
// Save Messages
// =========================================

const oldAddMessage =
	addMessage;

addMessage = function(

	message,

	sender="bot",

	typing=false

){

	saveChatMessage(

		message,

		sender

	);

	oldAddMessage(

		message,

		sender,

		typing

	);

};

// =========================================
// Clear Chat
// =========================================

function clearChat(){

	localStorage.removeItem(
		"chat_history"
	);

	chatBody.innerHTML="";

	addMessage(

		"👋 Chat cleared. How can I help you?",

		"bot",

		true

	);

}

// =========================================
// Export Chat
// =========================================

function exportChat(){

	let history =
		JSON.parse(

			localStorage.getItem(
				"chat_history"
			)

		)
		||
		[];

	let text =
		"";

	history.forEach(item=>{

		text +=

		item.sender.toUpperCase()

		+

		": "

		+

		item.message

		+

		"\n\n";

	});

	const blob =
		new Blob(

			[text],

			{
				type:
				"text/plain"

			}

		);

	const url =
		URL.createObjectURL(
			blob
		);

	const link =
		document.createElement(
			"a"
		);

	link.href=url;

	link.download =
		"chat-history.txt";

	link.click();

}

// =========================================
// Initialize
// =========================================

function startChatInit(){
	try{ initChat(); }catch(e){ console.error('initChat error',e); }
}

if(document.readyState === 'loading'){
	document.addEventListener("DOMContentLoaded", startChatInit);
}else{
	startChatInit();
}

// ==========================================
// Draggable Chatbot
// ==========================================

function makeDraggable(element){

	if(!element){
		return;
	}

	let offsetX = 0;
	let offsetY = 0;
	let isDragging = false;
	let movedDuringDrag = false;

	function ensurePositioning(){
		try{
			const rect = element.getBoundingClientRect();
			if(!element.style.left || element.style.left === ""){
				element.style.left = rect.left + 'px';
			}
			if(!element.style.top || element.style.top === ""){
				element.style.top = rect.top + 'px';
			}
			if(!element.style.position || element.style.position === ""){
				element.style.position = 'fixed';
			}
			element.style.right = 'auto';
			element.style.bottom = 'auto';
		}catch(e){ }
	}

	// mouse support
	element.addEventListener("mousedown", function(e){
		e.preventDefault();
		ensurePositioning();
		isDragging = true;
		movedDuringDrag = false;
		const rect = element.getBoundingClientRect();
		offsetX = e.clientX - rect.left;
		offsetY = e.clientY - rect.top;
		element.style.cursor = "grabbing";
	});

	document.addEventListener("mousemove", function(e){
		if(!isDragging) return;
		let x = e.clientX - offsetX;
		let y = e.clientY - offsetY;
		// Keep inside screen
		if(x < 0) x = 0;
		if(y < 0) y = 0;
		if(x + element.offsetWidth > window.innerWidth) x = window.innerWidth - element.offsetWidth;
		if(y + element.offsetHeight > window.innerHeight) y = window.innerHeight - element.offsetHeight;
		element.style.left = x + "px";
		element.style.top = y + "px";
		element.style.right = "auto";
		element.style.bottom = "auto";
		movedDuringDrag = true;
	});

	element.addEventListener("click", function(e){
		if(movedDuringDrag){
			e.preventDefault();
			e.stopPropagation();
			movedDuringDrag = false;
		}
	});

	document.addEventListener("mouseup", function(){
		isDragging = false;
		element.style.cursor = "grab";
	});

	// touch support
	element.addEventListener("touchstart", function(e){
		if(!e.touches || !e.touches[0]) return;
		const t = e.touches[0];
		ensurePositioning();
		isDragging = true;
		const rect = element.getBoundingClientRect();
		offsetX = t.clientX - rect.left;
		offsetY = t.clientY - rect.top;
		element.style.cursor = "grabbing";
	}, {passive:false});

	document.addEventListener("touchmove", function(e){
		if(!isDragging) return;
		if(!e.touches || !e.touches[0]) return;
		const t = e.touches[0];
		let x = t.clientX - offsetX;
		let y = t.clientY - offsetY;
		if(x < 0) x = 0;
		if(y < 0) y = 0;
		if(x + element.offsetWidth > window.innerWidth) x = window.innerWidth - element.offsetWidth;
		if(y + element.offsetHeight > window.innerHeight) y = window.innerHeight - element.offsetHeight;
		element.style.left = x + "px";
		element.style.top = y + "px";
		element.style.right = "auto";
		element.style.bottom = "auto";
		e.preventDefault();
	}, {passive:false});

	document.addEventListener("touchend", function(){
		isDragging = false;
		element.style.cursor = "grab";
	});

}

// Draggable activation moved into `initChat()` where elements exist



