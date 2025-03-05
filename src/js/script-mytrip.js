document.addEventListener("DOMContentLoaded", function () {
    const deleteButtons = document.querySelectorAll(".delete");

    deleteButtons.forEach(button => {
        button.addEventListener("click", function () {
            const listItem = this.closest(".list-item"); // หา list-item ที่ใกล้ที่สุด
            if (listItem) {
                listItem.remove(); // ลบรายการออก
            }
        });
    });
});
