function saveTrip() {
    const tripDataElement = document.getElementById('trip-data');

    if (!tripDataElement) {
        console.error("Error: trip-data element not found!");
        alert("เกิดข้อผิดพลาด: ไม่พบข้อมูลทริป");
        return;
    }

    const tripData = JSON.parse(tripDataElement.textContent);
    const provinceElement = document.querySelector('.location-header');
    tripData.province = provinceElement ? provinceElement.textContent.trim() : tripData.province;
    console.log("tripData ก่อน fetch:", tripData);

    fetch('/save_trip', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(tripData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert(data.error);
        } else {
            alert('บันทึกทริปสำเร็จ!');
            window.location.reload();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('เกิดข้อผิดพลาดในการบันทึกทริป');
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const tripBtn = document.querySelector('.trip-btn');
    if (tripBtn) {
        tripBtn.addEventListener('click', saveTrip);
    } else {
        console.error("Error: trip-btn element not found!");
    }
});
