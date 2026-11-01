import { expect, test } from "@playwright/test";
test("chief creates and approves declaration wording", async ({page}) => {
  const items: {id:string;title:string;declarations:string[];approved_at:string|null}[] = [];
  let approvals = 0;
  await page.route("**/api/v1/editorial/submission-checklists**", async route => {
    if (route.request().method() === "POST") {
      if (route.request().url().endsWith("/approve")) { approvals += 1; items[0].approved_at = "2026-10-23T12:00:00Z"; }
      else items.push({id:"policy-1",...route.request().postDataJSON(),approved_at:null});
    }
    await route.fulfill({json:{items}});
  });
  await page.goto("/editorial/checklist");
  await page.getByLabel("Checklist title").fill("Journal declarations");
  await page.getByLabel("Declarations, one per line").fill("Exact declaration A\nExact declaration B");
  await page.getByRole("button",{name:"Save draft checklist"}).click();
  await expect(page.getByText("Exact declaration A",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Approve this exact wording"}).click();
  const dialog = page.getByRole("dialog", {name:"Approve this exact declaration wording?"});
  await expect(dialog).toContainText("Journal declarations, version policy-1, containing 2 declarations");
  expect(approvals).toBe(0);
  await dialog.getByRole("button", {name:"Cancel", exact:true}).click();
  await expect(page.getByRole("button",{name:"Approve this exact wording"})).toBeEnabled();
  await page.getByRole("button",{name:"Approve this exact wording"}).click();
  await dialog.getByRole("button", {name:"Approve checklist", exact:true}).click();
  const current = page.getByRole("region", {name:"Current checklist", exact:true});
  await expect(current.getByText("Exact declaration A",{exact:true})).toBeVisible();
  await expect(current.getByText("Exact declaration B",{exact:true})).toBeVisible();
  await expect(current.getByText(/^Approved /)).toBeVisible();
  await expect(page.getByRole("region", {name:"Checklist versions", exact:true}).getByText("Current approved checklist",{exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Approve this exact wording"})).toHaveCount(0);
  expect(approvals).toBe(1);
});

test("author confirms current declarations and submits a saved draft", async ({page}) => {
  const draft = {id:"draft-1",reference:"NSAJ-TEST",status:"draft",title:"A study",abstract:"Abstract",keywords:["science"],manuscript_type:"original research",authors:[{full_name:"Author",affiliation:"Institute",email:"a@example.test"}],files:[],updated_at:null};
  let submitted = false;
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (path.endsWith("/auth/me")) body = {authenticated:true,display_name:"Author",roles:["author"]};
    else if (path.endsWith("/author/submission-checklist")) body = {checklist:{id:"policy-1",title:"Declarations",declarations:["Test declaration A","Test declaration B"]}};
    else if (path.endsWith("/author/submissions")) body = {items:submitted ? [] : [draft]};
    else if (path.endsWith("/author/workspace")) body = {items:submitted ? [{...draft,status:"submitted"}] : []};
    else if (path.endsWith("/editorial")) body = {...draft,status:"submitted",decisions:[],history:[{status:"submitted",created_at:"2026-10-23T12:00:00Z"}]};
    else if (path.endsWith("/receipt")) body = {reference:draft.reference,checklist_id:"policy-1",declarations:["Test declaration A","Test declaration B"],submitted_at:"2026-10-23T12:00:00Z"};
    else if (path.endsWith("/submit")) {
      expect(route.request().postDataJSON()).toEqual({checklist_id:"policy-1",acknowledged_indices:[0,1]});
      submitted = true; body = {reference:draft.reference,submitted_at:"2026-10-23T12:00:00Z"};
    }
    await route.fulfill({json:body});
  });
  await page.goto("/author");
  await expect(page.getByRole("button",{name:/NSAJ-TEST/})).toContainText("Paper ID: NSAJ-TEST");
  await page.getByRole("button",{name:/NSAJ-TEST/}).click();
  await expect(page.locator(".draft-editor").first().locator(".work-meta")).toHaveText("Paper ID: NSAJ-TEST / Draft");
  const submit = page.getByRole("button",{name:"Submit manuscript for editorial review",exact:true});
  await expect(submit).toBeDisabled();
  await page.getByLabel("Test declaration A").check();
  await page.getByLabel("Test declaration B").check();
  await expect(submit).toBeEnabled();
  await page.getByLabel("Manuscript title").fill("Unsaved edit");
  await expect(submit).toBeDisabled();
  await page.getByLabel("Manuscript title").fill("A study");
  await page.getByLabel("Test declaration A").check();
  await page.getByLabel("Test declaration B").check();
  await submit.click();
  const dialog = page.getByRole("dialog", {name:"Submit manuscript for editorial review?"});
  await expect(dialog).toContainText("NSAJ-TEST: A study");
  await expect(dialog).toContainText("version policy-1");
  expect(submitted).toBe(false);
  await dialog.getByRole("button", {name:"Cancel",exact:true}).click();
  await expect(page.getByLabel("Test declaration A")).toBeChecked();
  await expect(submit).toBeEnabled();
  await submit.click();
  await dialog.getByRole("button", {name:"Confirm submission",exact:true}).click();
  await expect(page.getByText(/Submitted NSAJ-TEST on/)).toBeVisible();
  await page.getByRole("button",{name:/NSAJ-TEST.*submitted/}).click();
  const receipt = page.locator(".submission-detail details").filter({hasText:"Submission receipt and declarations"});
  await receipt.locator("summary").click();
  await expect(receipt.getByText("Paper ID: NSAJ-TEST",{exact:true})).toBeVisible();
  await expect(receipt.getByText("Test declaration A",{exact:true})).toBeVisible();
});
