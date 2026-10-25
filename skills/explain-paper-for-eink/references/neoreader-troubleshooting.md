# NeoReader editing failures

Read this only when the user reports that NeoReader cannot add pages or edit a delivered PDF. Treat content/rendering validity and device editing compatibility as separate questions. Successful page insertion in a local library does not establish NeoReader compatibility.

## Diagnose the actual delivered file

1. Confirm the user opened the extracted ZIP copy through the same device, folder, and opening route as a working control.
2. Obtain the actual failing file copied back from the device. Compare its size, SHA-256, original-prefix equality, and incremental updates with the verified pre-delivery PDF. If the copy is unavailable, state that the delivery hypothesis remains untested.
3. Inspect encryption, edit/assemble permissions, signatures, page trees, cross-references, and catalog additions such as `/AF`, `/Names`, `/EmbeddedFiles`, `/C2PA_Manifest`, `/Perms`, `/AcroForm`, and `/ByteRange`. Preserve signed or credential-bearing originals as evidence.
4. Prefer a paired test inside one ZIP: A is the untouched pre-delivery PDF; B is the returned failing copy. Compare their extracted text and rendered content. Change one variable at a time and ask the user to test the pair on the device.
5. Test the actual reading edition through the same ZIP route before changing generators or rebuilding its content.

If evidence points to PDF structure and the user wants a structural workaround, a copy of a known-working PDF can be used to test appending sample pages, removing the initial pages, clearing stale destinations/document identity, and saving a new file. Verify the remaining pages and exclude unrelated annotations. Keep this as a diagnostic option, not the default production method.

## Recorded case and its limits

The predecessor workflow records the following observations from 14 October 2026:

- Five individually downloaded simple PDFs failed page insertion across several generation approaches. An unchanged paper control and two independent PDFs worked.
- A returned minimal PDF was 30,617 bytes; the 5,747-byte pre-delivery file remained its exact prefix. An incremental update added a Content Credentials attachment identified as C2PA. Editing permissions were unrestricted, and text and rendered pages matched.
- In a ZIP-delivered A/B comparison, the untouched original worked and the returned copy failed. The existing 99-page dark reading edition also worked when delivered unchanged in a ZIP.
- Removing custom page labels did not fix the failing individual download. A working-base append/delete test worked, but changing generators, PDF versions, or backgrounds was unnecessary once ZIP delivery worked.

These observations motivated the ZIP default. They implicate the added delivery update in that case but do not distinguish the attachment from the structure of its incremental update. They establish no universal rule for C2PA documents, BOOX devices, or firmware. Re-evaluate with the new failing bytes when behavior differs; report only tests actually performed in the current task.
