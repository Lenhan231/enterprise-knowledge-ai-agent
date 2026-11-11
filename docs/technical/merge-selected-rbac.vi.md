# Đưa riêng bản sửa RBAC từ Huy vào main

Đây là ghi chép lần tích hợp ngày 30/10/2026, không phải script cần chạy lại
sau khi PR đã merge. Không merge toàn bộ Huy vì nhánh còn nhiều benchmark lịch sử.

## Phạm vi

- Main nền: `beac2f3`.
- Lấy nội dung hai commit `489b641`, `2ecafb8` theo thứ tự.
- Ba file runtime: common eligibility SQL, parent expansion repository,
  parent retrieval dispatch; bốn file test; tài liệu policy và log kiểm chứng cuối.
- Bỏ HANDOFF riêng của Huy và log của policy admin cũ. Không lấy dataset,
  benchmark Review 2 hoặc merge commit `f17b195`.
- Chính sách cuối: active + ready luôn bắt buộc; role thường phải khớp ACL;
  admin có thể xem ACL rỗng/NULL nhưng vẫn chịu scope company/document/metadata.

## Các lệnh đã dùng

Từ repo chính, tạo worktree để không phải đổi nhánh làm việc Huy:

```bash
git fetch origin main Huy
git worktree add -b Huy-rbac-main /tmp/enterprise-rbac-main-integration origin/main
cd /tmp/enterprise-rbac-main-integration
```

Áp dụng commit nhưng chưa tạo commit. Cả hai lần đều chỉ conflict HANDOFF vì
main không có file này. Chọn không đưa HANDOFF riêng vào main:

```bash
git cherry-pick --no-commit 489b641
git rm artifacts/HANDOFF.md
git cherry-pick --quit

git cherry-pick --no-commit 2ecafb8
git rm artifacts/HANDOFF.md
git cherry-pick --quit

# Bỏ log của policy cũ, giữ log kiểm chứng policy cuối.
git rm -rf -- artifacts/evaluation/rbac-access-20261030
git diff --cached --stat
git diff --cached --check
```

`--quit` chỉ bỏ trạng thái cherry-pick, giữ các thay đổi đã áp dụng trong index.
Nếu có conflict ở source/test thì phải đọc và giải quyết, không chỉ chạy quit.

Sau khi chạy test và xem diff, người dùng đã yêu cầu tích hợp nên tạo commit,
push nhánh tạm, mở PR base=main và merge PR:

```bash
git add docs/technical/merge-selected-rbac.vi.md
git commit -m "fix: enforce document retrieval eligibility with admin ACL exception"
git push -u origin Huy-rbac-main
```

Kiểm tra lại PR chỉ có file cần thiết, chờ required checks nếu repository yêu cầu,
rồi merge bằng GitHub. Sau merge có thể xóa nhánh PR tạm; Huy vẫn là nhánh làm việc.

## Kiểm tra và triển khai

Chạy lại 41 test chọn lọc và 6 test PostgreSQL local trên chính bản tích hợp.
Các test PostgreSQL dùng database riêng, không dùng Supabase production. Không
chạy model inference hoặc tải weights. Log policy cuối ở
`artifacts/evaluation/rbac-admin-exception-20261030/` ghi checkpoint Huy gốc;
bản tích hợp dùng nguyên source/test tương ứng.

Merge GitHub không tự cập nhật container VPS. Cần kiểm tra working tree VPS,
pull main và rebuild/recreate đúng service theo quy trình deploy của nhóm.
Không reset --hard, xóa .env, hoặc tự migrate/index lại dữ liệu để deploy bản sửa này.
