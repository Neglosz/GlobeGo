const container = document.querySelector('.container');
const registerBtn = document.querySelector('.register-btn');
const loginBtn = document.querySelector('.login-btn');

registerBtn.addEventListener('click', () => {
    container.classList.add('active');
});

loginBtn.addEventListener('click', () => {
    container.classList.remove('active');
});

// static/js/main.js
function toggleDarkMode() {
    const isDarkMode = !document.body.classList.contains('dark-mode');
    document.body.classList.toggle('dark-mode');
    
    // อัปเดต cookie
    document.cookie = `darkMode=${isDarkMode ? 'on' : 'off'}; path=/; max-age=31536000`;

    // อัปเดต toggle switch ด้วยแอนิเมชัน
    const toggleSwitch = document.getElementById('darkModeToggle');
    if (toggleSwitch) {
        toggleSwitch.classList.add('fade'); // ทำให้ข้อความจางหาย
        setTimeout(() => {
            toggleSwitch.textContent = isDarkMode ? 'ON' : 'OFF'; // เปลี่ยนข้อความ
            toggleSwitch.classList.remove('fade'); // ทำให้ข้อความกลับมาชัด
        }, 200); // เวลาตรงกับ transition (0.2 วินาที)
    }
}

// ตรวจสอบสถานะ Dark Mode เมื่อโหลดหน้า (ถ้าไม่ใช้ใน base.html)
if (document.cookie.includes('darkMode=on')) {
    document.body.classList.add('dark-mode');
}


