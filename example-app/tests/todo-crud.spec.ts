// @tags: smoke, crud
// @jira: PLAY-2
// @owner: team-qa
/**
 * Todo CRUD Tests
 *
 * PLAY-2: Add Todo — Verify users can add new todos
 * PLAY-3: Toggle Todo — Verify users can mark todos as complete/incomplete
 * PLAY-4: Delete Todo — Verify users can delete todos with confirmation
 * PLAY-6: Edit Todo — Verify users can edit todo text inline
 */
import { test, expect } from '@playwright/test';

// Helper: log in before each test
test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await page.locator('#email').fill('demo@test.com');
  await page.locator('#password').fill('password123');
  await page.getByTestId('login-button').click();
  await expect(page.locator('#todo-page')).toBeVisible();
});

test.describe('PLAY-2: Add Todo', () => {
  test('should add a todo using the Add button', async ({ page }) => {
    await page.getByTestId('new-todo-input').fill('Buy groceries');
    await page.getByTestId('add-todo-button').click();

    const items = page.getByTestId('todo-item');
    await expect(items).toHaveCount(1);
    await expect(items.first().getByTestId('todo-text')).toHaveText('Buy groceries');
  });

  test('should add a todo by pressing Enter', async ({ page }) => {
    await page.getByTestId('new-todo-input').fill('Walk the dog');
    await page.getByTestId('new-todo-input').press('Enter');

    await expect(page.getByTestId('todo-item')).toHaveCount(1);
    await expect(page.getByTestId('todo-text')).toHaveText('Walk the dog');
  });

  test('should not add an empty todo', async ({ page }) => {
    await page.getByTestId('add-todo-button').click();
    await expect(page.getByTestId('todo-item')).toHaveCount(0);

    // Whitespace only
    await page.getByTestId('new-todo-input').fill('   ');
    await page.getByTestId('add-todo-button').click();
    await expect(page.getByTestId('todo-item')).toHaveCount(0);
  });

  test('should clear input after adding a todo', async ({ page }) => {
    await page.getByTestId('new-todo-input').fill('Read a book');
    await page.getByTestId('add-todo-button').click();

    await expect(page.getByTestId('new-todo-input')).toHaveValue('');
  });

  test('should add multiple todos in order', async ({ page }) => {
    const items = ['First task', 'Second task', 'Third task'];
    for (const item of items) {
      await page.getByTestId('new-todo-input').fill(item);
      await page.getByTestId('add-todo-button').click();
    }

    const todoItems = page.getByTestId('todo-item');
    await expect(todoItems).toHaveCount(3);

    for (let i = 0; i < items.length; i++) {
      await expect(todoItems.nth(i).getByTestId('todo-text')).toHaveText(items[i]);
    }
  });

  test('should update the item count after adding', async ({ page }) => {
    await page.getByTestId('new-todo-input').fill('Task one');
    await page.getByTestId('add-todo-button').click();
    await expect(page.locator('#todo-count')).toContainText('1 item left');

    await page.getByTestId('new-todo-input').fill('Task two');
    await page.getByTestId('add-todo-button').click();
    await expect(page.locator('#todo-count')).toContainText('2 items left');
  });
});

test.describe('PLAY-3: Toggle Todo Complete', () => {
  test.beforeEach(async ({ page }) => {
    await page.getByTestId('new-todo-input').fill('Toggleable task');
    await page.getByTestId('add-todo-button').click();
  });

  test('should mark a todo as completed', async ({ page }) => {
    const item = page.getByTestId('todo-item').first();
    await item.getByTestId('todo-checkbox').check();

    await expect(item).toHaveClass(/completed/);
    await expect(item.getByTestId('todo-checkbox')).toBeChecked();
  });

  test('should apply strikethrough to completed todo text', async ({ page }) => {
    const item = page.getByTestId('todo-item').first();
    await item.getByTestId('todo-checkbox').check();

    const textEl = item.getByTestId('todo-text');
    await expect(textEl).toHaveCSS('text-decoration-line', 'line-through');
  });

  test('should unmark a completed todo', async ({ page }) => {
    const item = page.getByTestId('todo-item').first();
    const checkbox = item.getByTestId('todo-checkbox');

    // Complete then uncomplete
    await checkbox.check();
    await expect(item).toHaveClass(/completed/);

    await checkbox.uncheck();
    await expect(item).not.toHaveClass(/completed/);
    await expect(checkbox).not.toBeChecked();
  });

  test('should update the active count when toggling', async ({ page }) => {
    await expect(page.locator('#todo-count')).toContainText('1 item left');

    await page.getByTestId('todo-checkbox').first().check();
    await expect(page.locator('#todo-count')).toContainText('0 items left');

    await page.getByTestId('todo-checkbox').first().uncheck();
    await expect(page.locator('#todo-count')).toContainText('1 item left');
  });
});

test.describe('PLAY-4: Delete Todo', () => {
  test.beforeEach(async ({ page }) => {
    await page.getByTestId('new-todo-input').fill('Task to delete');
    await page.getByTestId('add-todo-button').click();
  });

  test('should show confirmation dialog on delete click', async ({ page }) => {
    await page.getByTestId('delete-todo').first().click();

    await expect(page.getByTestId('confirm-dialog')).toBeVisible();
    await expect(page.getByTestId('confirm-delete')).toBeVisible();
    await expect(page.getByTestId('cancel-delete')).toBeVisible();
  });

  test('should show the todo name in the confirmation dialog', async ({ page }) => {
    await page.getByTestId('delete-todo').first().click();

    const dialog = page.getByTestId('confirm-dialog');
    await expect(dialog).toContainText('Task to delete');
  });

  test('should delete the todo when confirmed', async ({ page }) => {
    await page.getByTestId('delete-todo').first().click();
    await page.getByTestId('confirm-delete').click();

    await expect(page.getByTestId('todo-item')).toHaveCount(0);
    await expect(page.getByTestId('confirm-dialog')).toHaveCount(0);
  });

  test('should not delete the todo when cancelled', async ({ page }) => {
    await page.getByTestId('delete-todo').first().click();
    await page.getByTestId('cancel-delete').click();

    await expect(page.getByTestId('todo-item')).toHaveCount(1);
    await expect(page.getByTestId('confirm-dialog')).toHaveCount(0);
  });

  test('should delete the correct todo from a list of many', async ({ page }) => {
    // Add more todos
    await page.getByTestId('new-todo-input').fill('Keep this one');
    await page.getByTestId('add-todo-button').click();
    await page.getByTestId('new-todo-input').fill('Also keep this');
    await page.getByTestId('add-todo-button').click();

    await expect(page.getByTestId('todo-item')).toHaveCount(3);

    // Delete the first one ("Task to delete")
    await page.getByTestId('delete-todo').first().click();
    await page.getByTestId('confirm-delete').click();

    await expect(page.getByTestId('todo-item')).toHaveCount(2);
    const texts = page.getByTestId('todo-text');
    await expect(texts.first()).toHaveText('Keep this one');
    await expect(texts.nth(1)).toHaveText('Also keep this');
  });
});

test.describe('PLAY-6: Edit Todo', () => {
  test.beforeEach(async ({ page }) => {
    await page.getByTestId('new-todo-input').fill('Original text');
    await page.getByTestId('add-todo-button').click();
  });

  test('should enter edit mode on double-click', async ({ page }) => {
    const textEl = page.getByTestId('todo-text').first();
    await textEl.dblclick();

    await expect(textEl).toHaveAttribute('contenteditable', 'true');
    await expect(textEl).toHaveClass(/editing/);
  });

  test('should save changes on Enter', async ({ page }) => {
    const textEl = page.getByTestId('todo-text').first();
    await textEl.dblclick();

    // Clear and type new text (Meta+A for macOS, Control+A for others)
    await page.keyboard.press('Meta+A');
    await page.keyboard.type('Updated text');
    await page.keyboard.press('Enter');

    await expect(textEl).toHaveText('Updated text');
    await expect(textEl).not.toHaveClass(/editing/);
  });

  test('should cancel edit on Escape', async ({ page }) => {
    const textEl = page.getByTestId('todo-text').first();
    await textEl.dblclick();

    await page.keyboard.press('Meta+A');
    await page.keyboard.type('This will be cancelled');
    await page.keyboard.press('Escape');

    await expect(textEl).toHaveText('Original text');
    await expect(textEl).not.toHaveClass(/editing/);
  });

  test('should save on blur (clicking away)', async ({ page }) => {
    const textEl = page.getByTestId('todo-text').first();
    await textEl.dblclick();

    await page.keyboard.press('Meta+A');
    await page.keyboard.type('Blur-saved text');

    // Click elsewhere to trigger blur
    await page.getByRole('heading', { name: 'My Todos' }).click();

    await expect(textEl).toHaveText('Blur-saved text');
    await expect(textEl).not.toHaveClass(/editing/);
  });

  test('should not save empty text', async ({ page }) => {
    const textEl = page.getByTestId('todo-text').first();
    await textEl.dblclick();

    await page.keyboard.press('Meta+A');
    await page.keyboard.press('Backspace');
    await page.keyboard.press('Enter');

    // Should revert to original
    await expect(textEl).toHaveText('Original text');
  });
});
