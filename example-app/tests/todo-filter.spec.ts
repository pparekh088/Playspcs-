// @tags: filter
// @jira: PLAY-5
// @owner: team-qa
/**
 * Todo Filter Tests
 *
 * PLAY-5: Filter Todos — Verify users can filter by All, Active, and Completed
 */
import { test, expect } from '@playwright/test';

test.describe('PLAY-5: Filter Todos', () => {
  // Log in and seed three todos: two active, one completed
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.locator('#email').fill('demo@test.com');
    await page.locator('#password').fill('password123');
    await page.getByTestId('login-button').click();
    await expect(page.locator('#todo-page')).toBeVisible();

    // Add todos
    const todos = ['Buy milk', 'Clean house', 'Write tests'];
    for (const text of todos) {
      await page.getByTestId('new-todo-input').fill(text);
      await page.getByTestId('add-todo-button').click();
    }

    // Mark "Clean house" as completed
    await page.getByTestId('todo-item').nth(1).getByTestId('todo-checkbox').check();
  });

  test('should show all todos by default (All filter)', async ({ page }) => {
    await expect(page.getByTestId('filter-all')).toHaveClass(/active/);
    await expect(page.getByTestId('todo-item')).toHaveCount(3);
  });

  test('should filter to show only active todos', async ({ page }) => {
    await page.getByTestId('filter-active').click();

    await expect(page.getByTestId('filter-active')).toHaveClass(/active/);
    await expect(page.getByTestId('todo-item')).toHaveCount(2);

    const texts = page.getByTestId('todo-text');
    await expect(texts.first()).toHaveText('Buy milk');
    await expect(texts.nth(1)).toHaveText('Write tests');
  });

  test('should filter to show only completed todos', async ({ page }) => {
    await page.getByTestId('filter-completed').click();

    await expect(page.getByTestId('filter-completed')).toHaveClass(/active/);
    await expect(page.getByTestId('todo-item')).toHaveCount(1);
    await expect(page.getByTestId('todo-text').first()).toHaveText('Clean house');
  });

  test('should switch back to All filter', async ({ page }) => {
    await page.getByTestId('filter-completed').click();
    await expect(page.getByTestId('todo-item')).toHaveCount(1);

    await page.getByTestId('filter-all').click();
    await expect(page.getByTestId('todo-item')).toHaveCount(3);
    await expect(page.getByTestId('filter-all')).toHaveClass(/active/);
  });

  test('should highlight the active filter tab', async ({ page }) => {
    // All is active by default
    await expect(page.getByTestId('filter-all')).toHaveClass(/active/);
    await expect(page.getByTestId('filter-active')).not.toHaveClass(/active/);
    await expect(page.getByTestId('filter-completed')).not.toHaveClass(/active/);

    // Click Active
    await page.getByTestId('filter-active').click();
    await expect(page.getByTestId('filter-all')).not.toHaveClass(/active/);
    await expect(page.getByTestId('filter-active')).toHaveClass(/active/);

    // Click Completed
    await page.getByTestId('filter-completed').click();
    await expect(page.getByTestId('filter-active')).not.toHaveClass(/active/);
    await expect(page.getByTestId('filter-completed')).toHaveClass(/active/);
  });

  test('should show empty state when no todos match filter', async ({ page }) => {
    // Complete all remaining active todos from the "All" view
    // "Buy milk" (nth 0) and "Write tests" (nth 2) are active
    await page.getByLabel('Toggle Buy milk').check();
    await page.getByLabel('Toggle Write tests').check();

    await page.getByTestId('filter-active').click();

    await expect(page.getByTestId('todo-item')).toHaveCount(0);
    await expect(page.locator('.empty-state')).toBeVisible();
    await expect(page.locator('.empty-state')).toContainText('No active todos');
  });

  test('should update filtered view when a todo is toggled', async ({ page }) => {
    // View active only
    await page.getByTestId('filter-active').click();
    await expect(page.getByTestId('todo-item')).toHaveCount(2);

    // Complete one active todo (use click instead of check since re-render removes it from view)
    await page.getByLabel('Toggle Buy milk').click();
    await expect(page.getByTestId('todo-item')).toHaveCount(1);
  });

  test('should maintain item count across filter changes', async ({ page }) => {
    // 2 active out of 3 total
    await expect(page.locator('#todo-count')).toContainText('2 items left out of 3');

    await page.getByTestId('filter-active').click();
    await expect(page.locator('#todo-count')).toContainText('2 items left out of 3');

    await page.getByTestId('filter-completed').click();
    await expect(page.locator('#todo-count')).toContainText('2 items left out of 3');
  });
});
