# E-Commerce Platform

## Overview

We are building a full e-commerce platform that lets merchants list products and
customers browse, search, and purchase them online. This document specifies the
initial end-to-end shopping experience along with the merchant-facing admin
tooling required to operate the store. The platform must support the complete
journey from product discovery through checkout, payment, fulfillment, and
post-purchase engagement.

## Product Catalog

The catalog is the foundation of the store. Merchants must be able to create,
edit, and delete products. Each product has a name, description, one or more
images, a price, a SKU, and a category. Products can belong to a category, and
categories form the browsable structure of the storefront. Customers browse the
catalog by category and view a product detail page showing all product
information and images.

## Search and Filtering

Customers must be able to search the catalog by keyword against product names and
descriptions. Search results must be filterable by category, by price range, and
sortable by price and by newest. Filtering and search should work together so a
customer can, for example, search "shoes" and then filter to a price range.

## Shopping Cart

Customers add products to a shopping cart. The cart persists across sessions for
logged-in users. Customers can update the quantity of any line item or remove a
line item entirely. The cart displays a running subtotal.

## Checkout

From the cart, a customer proceeds to checkout. Checkout collects a shipping
address and a billing address, shows an order summary including shipping cost and
total, and requires the customer to be authenticated. Checkout must not be
possible when the cart is empty. Checkout depends on the cart and on shipping
cost calculation being available.

## Shipping Calculation

The platform calculates a shipping cost for an order based on the destination
address and the total order weight. The calculated shipping cost is shown during
checkout and included in the order total.

## Payment

Payment is processed through Stripe. During checkout, after the order summary,
the customer enters card details and the platform charges the order total via
Stripe. A successful charge moves the order into a paid state; a failed charge
keeps the customer on the payment step with an error. Payment depends on
checkout.

## Order Management

When payment succeeds, the platform creates an order record capturing the line
items, addresses, shipping cost, and total. Customers can view their order
history and the status of each order (paid, shipping, delivered, cancelled).
Merchants can view all orders and update an order's status. Order management
depends on payment.

## Inventory

Each product tracks an available stock quantity. When an order is placed, the
stock for each purchased product is decremented. Products with zero stock are
shown as out of stock and cannot be added to the cart. Inventory decrement
depends on order creation.

## Email Receipts

After an order is successfully paid, the platform sends the customer an email
receipt containing the order number, line items, totals, and shipping address.
Email receipts depend on order creation.

## Reviews and Ratings

Customers who have purchased a product may leave a star rating (1-5) and a
written review on that product's detail page. The product detail page shows the
average rating and the list of reviews. A customer may only review a product they
have purchased.

## Wishlist

Logged-in customers can add products to a personal wishlist and remove them.
Wishlist items are viewable on a dedicated wishlist page, and a product can be
moved from the wishlist into the cart.

## Admin Panel

Merchants access an admin panel to manage the store. The admin panel provides
product management (create/edit/delete), category management, order management
(view and update status), and inventory visibility. Access to the admin panel is
restricted to merchant accounts.

## Out of Scope

Multi-currency, promotions/coupons, and returns processing are out of scope for
this release.
